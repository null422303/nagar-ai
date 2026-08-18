import base64
from typing import Optional

from fastapi import APIRouter, UploadFile, File, Form

from app.engines import dedup
from app.models import store
from app.services import intake

router = APIRouter()


@router.post("/complaints")
async def create_complaint(
    text: Optional[str] = Form(None),
    image: Optional[UploadFile] = File(None),
    audio: Optional[UploadFile] = File(None),
    lat: Optional[str] = Form(None),
    lng: Optional[str] = Form(None),
    language: Optional[str] = Form(""),
):
    image_b64 = base64.b64encode(await image.read()).decode() if image else ""
    audio_b64 = base64.b64encode(await audio.read()).decode() if audio else ""
    audio_ext = (audio.filename or "wav").split(".")[-1] if audio else "wav"

    if not (text and text.strip()) and not image_b64 and not audio_b64:
        from fastapi import HTTPException
        raise HTTPException(status_code=400, detail="Nothing to file — add text, a photo, or a voice note.")

    gps = None
    if lat is not None and lat != "" and lng is not None and lng != "":
        gps = {"lat": lat, "lng": lng}

    complaint = await intake.process_submission(
        text=text or "", image_b64=image_b64, audio_b64=audio_b64, audio_ext=audio_ext,
        gps=gps, language=language,
    )
    result = await dedup.ingest_complaint(complaint)
    complaint["id"] = result["complaint_id"]
    complaint["issue_id"] = result["issue_id"]
    return {"complaint": complaint, "dedup": result}

@router.post("/asr")
async def transcribe_only(audio: UploadFile = File(...), language: str = Form("")):
    """Fast transcribe-only endpoint (no translation/extraction/dedup).
    Used by the mic preview. Returns the verbatim thanglish/romanized transcript
    (e.g. "Vanakkam... Anna Nagar Second Avenue-le periya kuzhi irukku") so the
    preview box matches what was spoken — no English translation."""
    audio_b64 = base64.b64encode(await audio.read()).decode()
    audio_ext = (audio.filename or "wav").split(".")[-1]
    from app.services import ai
    asr = await ai.transcribe(audio_b64, format_hint=audio_ext, language=language)
    return {"transcript": asr["text"], "transcript_en": asr["text"]}


@router.get("/complaints")
async def list_complaints(issue_id: Optional[int] = None):
    import json as _json
    out = []
    for r in store.list_complaints(issue_id):
        d = dict(r)
        for k in ("lat", "lng"):
            if d.get(k) in ("", None):
                d[k] = None
        try:
            d["photo_meta"] = _json.loads(r.get("photo_meta") or "{}")
        except Exception:
            d["photo_meta"] = {}
        out.append(d)
    return out


_DEFAULT_LABELS = {
    "pothole": "Pothole", "garbage": "Garbage", "broken_streetlight": "Streetlight",
    "waterlogging": "Waterlogging", "other": "Other",
}
_DEFAULT_COLORS = {
    "pothole": "#E8503A", "garbage": "#2FA84F", "broken_streetlight": "#F2B705",
    "waterlogging": "#2B7FF5", "other": "#7A877A",
}


def _enrich_issue(d: dict) -> dict:
    """Fill category_label/category_color defaults for legacy rows."""
    cat = d.get("category") or "other"
    if not d.get("category_label") or d.get("category_label") == cat:
        d["category_label"] = _DEFAULT_LABELS.get(cat, d.get("category_label") or cat.replace("_", " ").title())
    if not d.get("category_color"):
        d["category_color"] = _DEFAULT_COLORS.get(cat, "#7A877A")
    return d


@router.get("/issues")
async def list_issues(category: Optional[str] = None, status: Optional[str] = None,
                      sort: str = "priority"):
    out = []
    for r in store.query_issues(category=category, status=status, sort=sort):
        d = _enrich_issue(dict(r))
        d["members"] = store.get_memberships(int(r["id"]))
        out.append(d)
    return out


@router.get("/issues/{issue_id}")
async def get_issue(issue_id: int):
    r = store.get_issue(issue_id)
    if not r:
        return {"error": "not found"}
    d = dict(r)
    d["members"] = store.get_memberships(issue_id)
    return _enrich_issue(d)


@router.post("/issues/{issue_id}/status")
async def update_status(issue_id: int, status: str, dept: Optional[str] = None):
    issue = store.get_issue(issue_id)
    if not issue:
        return {"error": "not found"}
    store.update_issue(issue_id, status=status)
    if dept:
        store.update_issue(issue_id, dept=dept)
    for m in store.get_memberships(issue_id):
        store.update_complaint(int(m["complaint_id"]), status=status)
    return {"ok": True, "issue_id": issue_id, "status": status}


@router.post("/issues/{issue_id}/verify")
async def verify_issue(issue_id: int, image: UploadFile = File(...)):
    """Citizen photo-verification close-loop: is it actually fixed?"""
    from app.engines.dedup import _text_overlap
    import base64 as b64
    image_b64 = b64.b64encode(await image.read()).decode()
    vision = await intake._analyze_photo(image_b64)
    issue = store.get_issue(issue_id)
    if not issue:
        return {"error": "issue not found"}
    # compare new photo fingerprint against the issue's centroid vision fingerprint
    old_fp = issue.get("centroid_vision") or ""
    overlap = _text_overlap(vision.vision_fingerprint, old_fp)
    verdict = "looks_resolved" if overlap < 0.3 else "still_unresolved"
    return {
        "issue_id": issue_id,
        "category_seen": vision.category,
        "severity_seen": vision.severity,
        "verdict": verdict,
        "fingerprint_overlap": round(overlap, 2),
        "note": "if still_unresolved, the issue stays open and citizens are notified again",
    }


@router.get("/status/{complaint_id}")
async def public_status(complaint_id: int):
    """Shareable citizen status page endpoint."""
    row = store.get_complaint(complaint_id)
    if not row:
        return {"error": "not found"}
    d = dict(row)
    issue = None
    if row.get("issue_id"):
        issue = store.get_issue(int(row["issue_id"]))
        d["issue"] = _enrich_issue(dict(issue)) if issue else None
        # department/SLA live on the issue — surface them on the ticket too
        if issue and not d.get("dept"):
            d["dept"] = issue.get("dept")
        if issue and not d.get("sla_deadline"):
            d["sla_deadline"] = issue.get("sla_deadline")
    return d


@router.get("/health")
async def health():
    from app.services.ai import Cache, _DS_KEYS
    return {"ok": True, "cache_entries": Cache.size(), "dashscope_keys": len(_DS_KEYS)}


@router.post("/reset")
async def reset_board():
    """Wipe all complaints/issues/memberships (keeps CSV headers + poi cache)."""
    store.reset_all()
    return {"ok": True, "reset": True}


@router.get("/search")
async def search_issues(
    category: Optional[str] = None,
    status: Optional[str] = None,
    dept: Optional[str] = None,
    min_severity: Optional[int] = None,
    q: Optional[str] = None,
    min_affected: Optional[int] = None,
    sla_breached: Optional[bool] = None,
    sort: str = "priority",
    limit: Optional[int] = None,
):
    """Rich query over issues: filters + text search + sort + limit."""
    out = []
    for r in store.query_issues(
        category=category, status=status, dept=dept,
        min_severity=min_severity, search=q, min_affected=min_affected,
        sla_breached=sla_breached, sort=sort, limit=limit,
    ):
        d = _enrich_issue(dict(r))
        d["members"] = store.get_memberships(int(r["id"]))
        out.append(d)
    return out


@router.get("/stats")
async def get_stats():
    """Aggregated dashboard KPIs (counts, affected, by category, avg priority)."""
    return store.issue_stats()


@router.get("/recent")
async def get_recent(n: int = 10, category: Optional[str] = None):
    """Latest complaints (newest first), optionally filtered by category."""
    return store.recent_complaints(n=n, category=category)
