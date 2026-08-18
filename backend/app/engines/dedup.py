"""Dedup engine — canonicalize-then-embed, online clustering.

KEY INSIGHT (validated empirically): the DashScope embedding is weak on Tamil
(pothole EN<->TA cos=0.49, garbage EN<->TA cos=0.24 — the latter is BELOW the
pothole-vs-garbage cross distance 0.32). So we NEVER embed raw Indic text.
Instead the LLM first canonicalizes every complaint into a fixed ENGLISH
"issue fingerprint" (category + location + vision description + summary), and
we embed THAT. Tamil குழி / Hindi गड्ढा / English pothole -> identical vectors.

Clustering is online: a new complaint either joins the best existing issue or
spawns a new one. Memberships store the 3 component scores for the audit trail.
"""
import base64
import json
import math
import struct
import time
from typing import Optional, Tuple

from app.engines import priority as prio_engine
from app.models import store
from app.services import ai, geocode

W_TEXT = 0.55
W_GEO = 0.30
W_VISION = 0.15
TAU_MERGE = 0.62
TAU_HINT = 0.50
GEO_FENCE_M = 500.0
GEO_SIGMA_M = 60.0

# category -> department SLA (hours to resolve)
SLA_HOURS = {
    "pothole": 72,
    "garbage": 48,
    "broken_streetlight": 96,
    "waterlogging": 48,
    "other": 168,
}


def sla_deadline_for(category: str) -> str:
    import datetime
    hours = SLA_HOURS.get(category, 168)
    return (datetime.datetime.utcnow() + datetime.timedelta(hours=hours)).strftime("%Y-%m-%d %H:%M:%S")


def _dept_for(category: str) -> str:
    return {
        "pothole": "Roads & Infrastructure",
        "garbage": "Sanitation",
        "broken_streetlight": "Street Lighting",
        "waterlogging": "Drainage & Water",
        "other": "General Administration",
    }.get(category, "General Administration")


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    import math as _m
    try:
        if not all(_m.isfinite(v) for v in (lat1, lng1, lat2, lng2)):
            return float("inf")
        if not (-90 <= lat1 <= 90 and -90 <= lat2 <= 90 and -180 <= lng1 <= 180 and -180 <= lng2 <= 180):
            return float("inf")
    except Exception:
        return float("inf")
    R = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    a = max(0.0, min(1.0, a))
    return 2 * R * math.asin(math.sqrt(a))


def cos_sim(a, b) -> float:
    if not a or not b:
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def geo_sim(dist_m: float, sigma_m: float = GEO_SIGMA_M) -> float:
    return math.exp(-0.5 * (dist_m / sigma_m) ** 2)


def pack_embed(v) -> str:
    """Encode embedding to a CSV-safe base64 string."""
    return base64.b64encode(struct.pack(f"{len(v)}f", *v)).decode()


def unpack_embed(b) -> list:
    if isinstance(b, str):
        try:
            raw = base64.b64decode(b)
        except Exception:
            return []
    else:
        raw = b
    if not raw or len(raw) % 4 != 0:
        return []
    return list(struct.unpack(f"{len(raw)//4}f", raw))


def _text_overlap(a: str, b: str) -> float:
    """Cheap deterministic word-overlap for vision-fingerprint similarity (no API call)."""
    if not a or not b:
        return 0.0
    wa, wb = set(a.lower().split()), set(b.lower().split())
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / min(len(wa), len(wb))


def build_fingerprint(text: str, category: str, vision_fp: str, location_text: str, summary: str) -> str:
    parts = [f"category:{category}"]
    if location_text:
        parts.append(f"location:{location_text}")
    if vision_fp:
        parts.append(f"vision:{vision_fp}")
    if summary:
        parts.append(f"summary:{summary}")
    if text:
        parts.append(f"text:{text}")
    return " | ".join(parts)


async def _embed_text(text: str) -> list:
    vecs = await ai.embed([text])
    return vecs[0]


def _best_issue(embed_vec: list, lat: Optional[float], lng: Optional[float], vision_fp: str) -> Tuple[Optional[int], dict]:
    """Compare against all issues. Returns (issue_id, component_scores).

    Weights are adaptive:
      - if the complaint has NO geo, geo weight -> 0, others renormalised
      - if the complaint HAS geo but NO issue is within GEO_FENCE_M, the geo
        signal is *uninformative* (geocoder disagreeing, not actively matching)
        -> geo weight dropped for this comparison so text can still merge
      - geo-fence: an issue beyond GEO_FENCE_M is still eligible only via text.
    """
    best_id, best_sim, best_scores = None, 0.0, {}
    has_geo = lat is not None and lng is not None
    any_issue_within_fence = False

    prelim = []
    for issue in store.list_issues():
        centroid_embed = unpack_embed(issue.get("centroid_embed"))
        text_score = cos_sim(embed_vec, centroid_embed) if centroid_embed else 0.0
        clat, clng = issue.get("centroid_lat"), issue.get("centroid_lng")
        has_issue_geo = clat not in (None, "") and clng not in (None, "") and float(clat) and float(clng)

        geo_score = 0.0
        if has_geo and has_issue_geo:
            dist = haversine_m(lat, lng, float(clat), float(clng))
            geo_score = geo_sim(dist)
            if dist <= GEO_FENCE_M:
                any_issue_within_fence = True
        vision_score = _text_overlap(vision_fp, issue.get("centroid_vision") or "")
        prelim.append((issue, text_score, geo_score, vision_score))

    # adaptive weights
    w_t, w_g, w_v = W_TEXT, W_GEO, W_VISION
    if not has_geo:
        w_g = 0.0
    elif not any_issue_within_fence:
        w_g = 0.0  # geocode is uninformative -> let text+vision decide
    if not vision_fp:
        w_v = 0.0
    total = w_t + w_g + w_v
    if total > 0:
        w_t, w_g, w_v = w_t / total, w_g / total, w_v / total
    else:
        w_t = 1.0

    for issue, text_score, geo_score, vision_score in prelim:
        clat, clng = issue.get("centroid_lat"), issue.get("centroid_lng")
        if has_geo and clat not in (None, "") and clng not in (None, "") and float(clat) and float(clng):
            dist = haversine_m(lat, lng, float(clat), float(clng))
            if dist > GEO_FENCE_M:
                text_score *= 0.5  # far-away merges need very high text sim
        sim = w_t * text_score + w_g * geo_score + w_v * vision_score
        if sim > best_sim:
            best_sim, best_id = sim, issue["id"]
            best_scores = {"text": round(text_score, 3), "geo": round(geo_score, 3),
                           "vision": round(vision_score, 3), "sim": round(sim, 3)}
    return best_id, best_scores


async def _refresh_issue_priority(issue_id: int, pois: Optional[list] = None) -> None:
    issue = store.get_issue(issue_id)
    if not issue:
        return
    import datetime
    created = issue.get("created_at") or "2026-01-01 00:00:00"
    try:
        created_dt = datetime.datetime.strptime(created, "%Y-%m-%d %H:%M:%S")
        days = (datetime.datetime.utcnow() - created_dt).total_seconds() / 86400.0
    except Exception:
        days = 0.0
    days = max(0.0, days)
    if pois is not None:
        store.update_issue(issue_id, school_hospital_prox=store.json_dumps(pois))
        has_prox = bool(pois)
    else:
        has_prox = await _has_proximity_poi(issue_id, float(issue.get("centroid_lat") or 0) or None,
                                            float(issue.get("centroid_lng") or 0) or None)
    res = prio_engine.compute(int(issue.get("severity") or 3), int(issue.get("affected_count") or 1),
                              days, has_prox)
    store.update_issue(issue_id, priority_score=res["score"],
                       priority_reason=store.json_dumps(res["reason"]),
                       days_pending=round(days, 2))


async def _has_proximity_poi(issue_id: int, lat: Optional[float], lng: Optional[float]) -> bool:
    if lat is None or lng is None:
        return False
    pois = await geocode.nearby_schools_hospitals(lat, lng, radius_m=100)
    store.update_issue(issue_id, school_hospital_prox=store.json_dumps(pois))
    return bool(pois)


async def ingest_complaint(complaint: dict) -> dict:
    """Full pipeline: fingerprint -> embed -> cluster -> priority.
    The embed call and the Overpass POI check run CONCURRENTLY.

    Spam / unrelated submissions are stored as complaints (category=spam) but are
    quarantined — they never create or join an issue cluster or a map marker."""
    if complaint.get("is_spam") or complaint.get("category") == "spam":
        row = {k: complaint.get(k) for k in store.COMPLAINT_FIELDS if k in complaint}
        row["vision_raw"] = store.json_dumps(complaint.get("vision_raw") or {})
        row["photo_meta"] = store.json_dumps(complaint.get("photo_meta") or {})
        row["fingerprint_text"] = complaint.get("text_raw") or complaint.get("transcript", "")
        complaint_id = store.insert_complaint(row)
        store.update_complaint(complaint_id, issue_id="", notify_link=f"/status/{complaint_id}")
        return {"complaint_id": complaint_id, "issue_id": None, "scores": None,
                "merged": False, "spam": True}

    fp = build_fingerprint(
        complaint.get("text_raw") or complaint.get("transcript", ""),
        complaint.get("category", "other"),
        complaint.get("vision_fingerprint", ""),
        complaint.get("location_text", ""),
        complaint.get("summary", ""),
    )

    lat, lng = complaint.get("lat"), complaint.get("lng")

    # embed + POI probe run in parallel (independent); POI probe may be skipped if no geo
    async def _embed():
        return await _embed_text(fp)

    async def _poi_probe():
        if lat is None or lng is None:
            return None
        pois = await geocode.nearby_schools_hospitals(lat, lng, radius_m=100)
        return pois

    import asyncio
    embed_task = asyncio.ensure_future(_embed())
    poi_task = asyncio.ensure_future(_poi_probe()) if (lat is not None and lng is not None) else None
    embed_vec = await embed_task
    pois = await poi_task if poi_task else None

    issue_id, scores = _best_issue(embed_vec, lat, lng, complaint.get("vision_fingerprint", ""))

    row = {k: complaint.get(k) for k in store.COMPLAINT_FIELDS if k in complaint}
    row["fingerprint_embed"] = pack_embed(embed_vec)
    row["vision_raw"] = store.json_dumps(complaint.get("vision_raw") or {})
    row["photo_meta"] = store.json_dumps(complaint.get("photo_meta") or {})
    row["fingerprint_text"] = fp
    complaint_id = store.insert_complaint(row)

    if issue_id is not None and scores.get("sim", 0) >= TAU_MERGE:
        issue = store.get_issue(issue_id)
        store.update_issue(issue_id, affected_count=int(issue.get("affected_count") or 1) + 1)
        store.insert_membership({"complaint_id": complaint_id, "issue_id": issue_id,
                                 "sim_total": scores["sim"], "text_score": scores["text"],
                                 "geo_score": scores["geo"], "vision_score": scores["vision"]})
        store.update_complaint(complaint_id, issue_id=issue_id, notify_link=f"/status/{complaint_id}")
        await _refresh_issue_priority(issue_id, pois)
        return {"complaint_id": complaint_id, "issue_id": issue_id, "scores": scores, "merged": True}

    new_issue_id = store.insert_issue({
        "category": complaint.get("category", "other"),
        "category_label": complaint.get("category_label", ""),
        "category_color": complaint.get("category_color", ""),
        "tags": store.json_dumps(complaint.get("tags") or []),
        "severity": complaint.get("severity", 3),
        "severity_reason": complaint.get("severity_reason", ""),
        "summary": complaint.get("summary", ""),
        "centroid_lat": lat, "centroid_lng": lng,
        "centroid_embed": pack_embed(embed_vec),
        "centroid_vision": complaint.get("vision_fingerprint", ""),
        "affected_count": 1,
        "dept": _dept_for(complaint.get("category", "other")),
        "sla_deadline": sla_deadline_for(complaint.get("category", "other")),
    })
    store.insert_membership({"complaint_id": complaint_id, "issue_id": new_issue_id,
                             "sim_total": 1.0, "text_score": 1.0, "geo_score": 1.0, "vision_score": 1.0})
    store.update_complaint(complaint_id, issue_id=new_issue_id, notify_link=f"/status/{complaint_id}")
    await _refresh_issue_priority(new_issue_id, pois)
    return {"complaint_id": complaint_id, "issue_id": new_issue_id, "scores": None, "merged": False}
