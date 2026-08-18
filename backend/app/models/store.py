"""CSV-backed storage. Each table is a CSV file with a lock.

Tables: complaints, issues, memberships, poi_cache.
IDs are integer auto-increments derived from the max existing id.
"""
import csv
import json
import os
import threading
from pathlib import Path
from typing import Optional

SLA_DEFAULTS = {
    "pothole": 72,
    "garbage": 48,
    "broken_streetlight": 96,
    "waterlogging": 48,
    "other": 168,
}

from app.core.config import settings

_LOCK = threading.RLock()

COMPLAINT_FIELDS = [
    "id", "created_at", "channel", "language", "transcript", "transcript_en", "text_raw",
    "category", "category_conf", "category_label", "category_color", "severity", "severity_reason", "summary",
    "location_text", "lat", "lng", "loc_source", "loc_confidence",
    "vision_fingerprint", "fingerprint_embed", "vision_raw", "asr_confidence",
    "status", "dept", "sla_deadline", "notify_link", "issue_id",
    "photo_path", "audio_path", "photo_meta",
]

ISSUE_FIELDS = [
    "id", "created_at", "category", "category_label", "category_color", "severity", "severity_reason", "summary",
    "centroid_lat", "centroid_lng", "centroid_embed", "centroid_vision",
    "affected_count", "priority_score", "priority_reason", "status", "dept",
    "sla_deadline", "school_hospital_prox", "days_pending",
]

MEMBERSHIP_FIELDS = [
    "complaint_id", "issue_id", "sim_total", "text_score", "geo_score", "vision_score", "merged_at",
]

POI_FIELDS = ["lat", "lng", "kind", "name"]

_TABLES = {
    "complaints": COMPLAINT_FIELDS,
    "issues": ISSUE_FIELDS,
    "memberships": MEMBERSHIP_FIELDS,
    "poi_cache": POI_FIELDS,
}


def _path(table: str) -> Path:
    return settings.DB_PATH.parent / f"{table}.csv"


def _norm(row: dict, fields: list) -> dict:
    out = {}
    for f in fields:
        v = row.get(f)
        if v is None:
            out[f] = ""
        elif isinstance(v, str):
            out[f] = v.replace("\x00", "").replace("\r", " ").replace("\n", " ")
        else:
            out[f] = v
    return out


def _decode(row: dict) -> dict:
    d = dict(row)
    if not d.get("status"):
        d["status"] = "open"
    for k in ("lat", "lng", "centroid_lat", "centroid_lng"):
        if k in d and d[k] not in ("", None):
            try:
                d[k] = float(d[k])
            except ValueError:
                d[k] = None
    for k in ("affected_count", "priority_score", "days_pending", "sim_total",
              "text_score", "geo_score", "vision_score", "severity", "category_conf"):
        if k in d and d[k] not in ("", None):
            try:
                d[k] = float(d[k])
            except ValueError:
                pass
    for k in ("issue_id", "id", "complaint_id"):
        if k in d and d[k] not in ("", None):
            try:
                d[k] = int(d[k])
            except ValueError:
                pass
    return d


def _read(table: str) -> list:
    p = _path(table)
    if not p.exists():
        return []
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return [_decode(r) for r in rows]


def _write(table: str, rows: list) -> None:
    fields = _TABLES[table]
    p = _path(table)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(_norm(r, fields))


def init_store() -> None:
    settings.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        for table, fields in _TABLES.items():
            p = _path(table)
            if not p.exists():
                with open(p, "w", newline="", encoding="utf-8") as f:
                    csv.writer(f).writerow(fields)


def reset_all() -> None:
    """Wipe complaint/issue/membership data (keeps CSV headers + poi cache)."""
    with _LOCK:
        for table in ("complaints", "issues", "memberships"):
            p = _path(table)
            with open(p, "w", newline="", encoding="utf-8") as f:
                csv.writer(f).writerow(_TABLES[table])


def _next_id(table: str, id_field: str = "id") -> int:
    rows = _read(table)
    ids = [int(r.get(id_field) or 0) for r in rows]
    return (max(ids) + 1) if ids else 1


# ---------------- complaints ----------------

def insert_complaint(row: dict) -> int:
    with _LOCK:
        cid = _next_id("complaints")
        row["id"] = cid
        row.setdefault("created_at", _now())
        row.setdefault("status", "open")
        rows = _read("complaints")
        rows.append(row)
        _write("complaints", rows)
        return cid


def update_complaint(cid: int, **fields) -> None:
    with _LOCK:
        rows = _read("complaints")
        for r in rows:
            if int(r.get("id") or 0) == cid:
                for k, v in fields.items():
                    r[k] = v
        _write("complaints", rows)


def get_complaint(cid: int) -> Optional[dict]:
    for r in _read("complaints"):
        if int(r.get("id") or 0) == cid:
            return r
    return None


def list_complaints(issue_id: Optional[int] = None) -> list:
    rows = _read("complaints")
    rows.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    if issue_id is not None:
        rows = [r for r in rows if int(r.get("issue_id") or 0) == issue_id]
    return rows


# ---------------- issues ----------------

def insert_issue(row: dict) -> int:
    with _LOCK:
        iid = _next_id("issues")
        row["id"] = iid
        row.setdefault("created_at", _now())
        row.setdefault("affected_count", 1)
        row.setdefault("status", "open")
        rows = _read("issues")
        rows.append(row)
        _write("issues", rows)
        return iid


def update_issue(iid: int, **fields) -> None:
    with _LOCK:
        rows = _read("issues")
        for r in rows:
            if int(r.get("id") or 0) == iid:
                for k, v in fields.items():
                    r[k] = v
        _write("issues", rows)


def get_issue(iid: int) -> Optional[dict]:
    for r in _read("issues"):
        if int(r.get("id") or 0) == iid:
            return r
    return None


def list_issues(category: Optional[str] = None, status: Optional[str] = None) -> list:
    rows = _read("issues")
    if category:
        rows = [r for r in rows if r.get("category") == category]
    if status:
        rows = [r for r in rows if r.get("status") == status]
    rows.sort(key=lambda r: float(r.get("priority_score") or 0), reverse=True)
    return rows


def query_issues(category: Optional[str] = None, status: Optional[str] = None,
                 dept: Optional[str] = None, min_severity: Optional[int] = None,
                 search: Optional[str] = None, min_affected: Optional[int] = None,
                 sla_breached: Optional[bool] = None, sort: str = "priority",
                 limit: Optional[int] = None) -> list:
    """Flexible CSV query over issues: filter + search + sort + limit.

    Supports: category, status, dept, min_severity, text search (summary/category),
    min affected_count, SLA breach flag, sort (priority/days/affected/created),
    and an optional row limit.
    """
    import datetime as _dt
    rows = _read("issues")

    def _days(r):
        try:
            d = _dt.datetime.strptime(r.get("created_at") or "", "%Y-%m-%d %H:%M:%S")
            return max(0.0, (_dt.datetime.utcnow() - d).total_seconds() / 86400.0)
        except Exception:
            return 0.0

    out = []
    for r in rows:
        if category and r.get("category") != category:
            continue
        if status and r.get("status") != status:
            continue
        if dept and (r.get("dept") or "").lower() != dept.lower():
            continue
        if min_severity is not None and int(r.get("severity") or 0) < min_severity:
            continue
        if min_affected is not None and int(r.get("affected_count") or 0) < min_affected:
            continue
        if sla_breached is not None:
            sla = SLA_DEFAULTS.get(r.get("category"), 168)
            breached = (_days(r) * 24) > sla
            if breached != sla_breached:
                continue
        if search:
            hay = f"{r.get('summary') or ''} {r.get('category') or ''} {r.get('category_label') or ''} {r.get('dept') or ''}"
            if search.lower() not in hay.lower():
                continue
        out.append(r)

    if sort == "days":
        out.sort(key=_days, reverse=True)
    elif sort == "affected":
        out.sort(key=lambda r: int(r.get("affected_count") or 0), reverse=True)
    elif sort == "created":
        out.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    elif sort == "severity":
        out.sort(key=lambda r: int(r.get("severity") or 0), reverse=True)
    else:
        out.sort(key=lambda r: float(r.get("priority_score") or 0), reverse=True)

    if limit is not None:
        out = out[:limit]
    return out


def issue_stats() -> dict:
    """Aggregated stats across all issues (dashboard KPIs)."""
    rows = _read("issues")
    total = len(rows)
    affected = sum(int(r.get("affected_count") or 0) for r in rows)
    open_count = sum(1 for r in rows if r.get("status") != "resolved")
    resolved = sum(1 for r in rows if r.get("status") == "resolved")
    by_category = {}
    for r in rows:
        c = r.get("category") or "other"
        by_category[c] = by_category.get(c, 0) + 1
    avg_priority = round(sum(float(r.get("priority_score") or 0) for r in rows) / total, 1) if total else 0.0
    return {
        "total_issues": total,
        "total_affected": affected,
        "open": open_count,
        "resolved": resolved,
        "avg_priority": avg_priority,
        "by_category": by_category,
    }


def recent_complaints(n: int = 10, category: Optional[str] = None) -> list:
    """Latest complaints, newest first, optionally filtered by category."""
    rows = _read("complaints")
    rows.sort(key=lambda r: r.get("created_at") or "", reverse=True)
    if category:
        rows = [r for r in rows if r.get("category") == category]
    return rows[:n]


# ---------------- memberships ----------------

def insert_membership(row: dict) -> None:
    with _LOCK:
        rows = _read("memberships")
        rows.append(row)
        _write("memberships", rows)


def get_memberships(issue_id: int) -> list:
    return [r for r in _read("memberships") if int(r.get("issue_id") or 0) == issue_id]


# ---------------- poi_cache ----------------

def get_pois(lat: float, lng: float) -> list:
    rlat, rlng = round(lat, 4), round(lng, 4)
    out = []
    for r in _read("poi_cache"):
        if abs(float(r.get("lat") or 0) - rlat) < 0.0005 and abs(float(r.get("lng") or 0) - rlng) < 0.0005:
            out.append({"name": r.get("name"), "kind": r.get("kind")})
    return out


def put_pois(lat: float, lng: float, pois: list) -> None:
    rlat, rlng = round(lat, 4), round(lng, 4)
    with _LOCK:
        rows = _read("poi_cache")
        existing = {(float(r.get("lat") or 0), float(r.get("lng") or 0)) for r in rows}
        if (rlat, rlng) in existing:
            return
        for p in pois:
            rows.append({"lat": rlat, "lng": rlng, "kind": p.get("kind"), "name": p.get("name")})
        _write("poi_cache", rows)


def _now() -> str:
    import datetime
    return datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def json_dumps(v) -> str:
    return json.dumps(v, ensure_ascii=False) if v else ""
