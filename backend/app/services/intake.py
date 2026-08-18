"""Intake service: turns raw (voice|photo|text) submissions into one structured complaint."""
import base64
import json
import re
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings
from app.models.schemas import ExtractedComplaint, VisionResult
from app.services import ai, geocode, photo_meta

EXTRACT_SYSTEM = (
    "You are the extraction engine of a civic complaint system for Chennai, India. "
    "From the user's complaint text (may be in Tamil, Hindi, English, or code-mixed), extract: "
    "category — use ONE of the standard keys (pothole|garbage|broken_streetlight|waterlogging|other) "
    "if it clearly fits; otherwise CREATE A NEW concise snake_case category key for an emerging issue "
    "(e.g. 'open_manhole', 'stray_cattle', 'electric_wire'). "
    "is_spam — true ONLY if the message is clearly unrelated to civic issues: personal disputes, "
    "advertising/promotions, spam/scams, complaints about neighbours/private property, politics, "
    "or anything a municipal corporation cannot act on. Otherwise false. "
    "When a complaint is vague or ambiguous (cannot be classified into any concrete issue) use "
    "category 'other'. "
    "Also give: category_label (human-friendly title, e.g. 'Open Manhole'), "
    "tags (2-4 short snake_case keywords describing the issue, e.g. ['asphalt','crater','two_wheeler']), "
    "severity 1-5, "
    "location_text (a short place name / landmark / street in Chennai), "
    "clean_summary (ONE clean English line that an official would understand), "
    "urgent_hint (true if it's a danger like live wires / open manhole / gas leak / fire). "
    "Reply with strict JSON only."
)

VISION_SYSTEM = (
    "You analyze civic-problem photos from India. Determine: category — use ONE of the standard keys "
    "(pothole|garbage|broken_streetlight|waterlogging|other) if it clearly fits; otherwise CREATE A NEW "
    "concise snake_case category key (e.g. 'open_manhole', 'stray_cattle'). "
    "is_spam — true ONLY if the photo is clearly not a civic issue (advertisement, personal photo, "
    "selfie, food, random object, unrelated scene). Otherwise false. "
    "When the photo is ambiguous/unclear use category 'other'. "
    "Also give category_label (human-friendly title), "
    "tags (2-4 short snake_case keywords, e.g. ['pothole','water','asphalt']), "
    "severity 1-5 based on size/extent/danger, "
    "extent (one short phrase like 'large pothole covering most of lane'), "
    "location_text (a short place name / landmark / street sign visible in the photo, in Chennai — "
    "empty string if none is visible), and "
    "vision_fingerprint (a neutral ONE-LINE English visual description used for similarity matching, "
    "e.g. 'large open pothole with water on asphalt road'). Reply with strict JSON only."
)

JSON_RE = re.compile(r"\{.*\}", re.DOTALL)

_DEFAULT_CAT_LABELS = {
    "pothole": "Pothole",
    "garbage": "Garbage",
    "broken_streetlight": "Streetlight",
    "waterlogging": "Waterlogging",
    "other": "Other",
}

_DEFAULT_CAT_COLORS = {
    "pothole": "#E8503A",
    "garbage": "#2FA84F",
    "broken_streetlight": "#F2B705",
    "waterlogging": "#2B7FF5",
    "other": "#7A877A",
    "spam": "#8B0000",
}

# Curated palette for dynamic (AI-created) categories — the app picks the color
# deterministically here (NOT the LLM) so colours are stable and never collide.
_DYNAMIC_PALETTE = [
    "#FF5A1F", "#9C27B0", "#00BCD4", "#E91E63", "#8BC34A",
    "#FF9800", "#3F51B5", "#00E676", "#FF4081", "#26A69A",
    "#7E57C2", "#FFB300", "#00ACC1", "#D81B60", "#689F38",
    "#FF7043", "#5C6BC0", "#00897B", "#FB8C00", "#8E24AA",
]


def _assign_category_color(category: str) -> str:
    """Deterministic, non-duplicate color for a dynamic category.
    Uses a fixed palette keyed by a hash of the category key, skipping any color
    already in use by existing categories."""
    import hashlib
    from app.models import store
    base = _DEFAULT_CAT_COLORS.get(category)
    if base:
        return base
    # colors already taken by existing categories (standard + dynamic + spam)
    used = set()
    for c in store.distinct_categories():
        col = (c.get("color") or "").strip().upper()
        if col:
            used.add(col)
    used.discard(_DEFAULT_CAT_COLORS.get(category, "").upper())
    h = int(hashlib.sha256(category.encode()).hexdigest(), 16)
    for i in range(len(_DYNAMIC_PALETTE)):
        col = _DYNAMIC_PALETTE[(h + i) % len(_DYNAMIC_PALETTE)]
        if col not in used:
            return col
    return _DYNAMIC_PALETTE[h % len(_DYNAMIC_PALETTE)]

# Indic scripts: Tamil (0B80-0BFF), Devanagari (0900-097F), Bengali, Telugu, etc.
_INDIC_RE = re.compile(r"[\u0900-\u0DFF\u0B00-\u0B7F]")


def _looks_non_en(text: str) -> bool:
    return bool(_INDIC_RE.search(text or ""))


def _sanitize_coords(lat, lng):
    """Validate GPS coords: finite numbers in valid lat/lng ranges. Returns (float, float)
    or (None, None) if invalid (NaN/Inf/out-of-range/partial)."""
    import math
    try:
        la, ln = float(lat), float(lng)
    except (TypeError, ValueError):
        return None, None
    if not (math.isfinite(la) and math.isfinite(ln)):
        return None, None
    if not (-90 <= la <= 90 and -180 <= ln <= 180):
        return None, None
    return la, ln


def _apply_orientation(image_b64: str, orientation) -> str:
    """Rotate the image per EXIF orientation (1-8) so the vision model sees it upright.
    Returns re-encoded base64, or the original if no orientation / conversion fails."""
    if not orientation:
        return image_b64
    try:
        from PIL import Image
        import base64 as _b64, io as _io
        img = Image.open(_io.BytesIO(_b64.b64decode(image_b64)))
        img = ImageOps_exif(img, int(orientation))
        buf = _io.BytesIO()
        img.convert("RGB").save(buf, format="JPEG", quality=92)
        return _b64.b64encode(buf.getvalue()).decode()
    except Exception:
        return image_b64


def ImageOps_exif(img, orientation):
    """Pillow ImageOps.exif_transpose equivalent (orientation 1-8)."""
    if orientation == 2:
        return img.transpose(__import__("PIL").Image.FLIP_LEFT_RIGHT)
    if orientation == 3:
        return img.transpose(__import__("PIL").Image.ROTATE_180)
    if orientation == 4:
        return img.transpose(__import__("PIL").Image.FLIP_TOP_BOTTOM)
    if orientation == 5:
        return img.transpose(__import__("PIL").Image.TRANSPOSE)
    if orientation == 6:
        return img.transpose(__import__("PIL").Image.ROTATE_270)
    if orientation == 7:
        return img.transpose(__import__("PIL").Image.TRANSVERSE)
    if orientation == 8:
        return img.transpose(__import__("PIL").Image.ROTATE_90)
    return img


def _parse_json(text: str) -> dict:
    m = JSON_RE.search(text)
    if not m:
        raise ValueError("no json in model output")
    return json.loads(m.group(0))


async def _extract_text(text: str) -> ExtractedComplaint:
    out = await ai.chat(
        f"Complaint text:\n{text}\n\nExtract.", system=EXTRACT_SYSTEM, json_mode=True, max_tokens=500)
    d = _parse_json(out)
    tags = d.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    return ExtractedComplaint(
        category=d.get("category", "other"),
        severity=int(d.get("severity", 3)),
        location_text=d.get("location_text", ""),
        clean_summary=d.get("clean_summary", text[:120]),
        urgent_hint=bool(d.get("urgent_hint", False)),
        category_label=d.get("category_label", ""),
        category_color=d.get("category_color", ""),
        tags=tags,
        is_spam=bool(d.get("is_spam", False)),
    )


async def _analyze_photo(image_b64: str) -> VisionResult:
    data_uri = f"data:image/jpeg;base64,{image_b64}"
    out = await ai.chat("Analyze this photo.", system=VISION_SYSTEM, json_mode=True,
                        max_tokens=400, images=[data_uri])
    d = _parse_json(out)
    tags = d.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    return VisionResult(
        category=d.get("category", "other"),
        severity=int(d.get("severity", 3)),
        extent=d.get("extent", ""),
        vision_fingerprint=d.get("vision_fingerprint", ""),
        location_text=d.get("location_text", ""),
        category_label=d.get("category_label", ""),
        category_color=d.get("category_color", ""),
        tags=tags,
        is_spam=bool(d.get("is_spam", False)),
    )


def _save_media(data_b64: str, ext: str) -> Path:
    fname = f"{uuid.uuid4().hex}.{ext}"
    path = settings.MEDIA_DIR / fname
    path.write_bytes(base64.b64decode(data_b64))
    return path


async def process_submission(text: str = "", image_b64: str = "", audio_b64: str = "",
                             audio_ext: str = "wav", gps: dict = None, language: str = "") -> dict:
    """Unified intake: any combination of text/photo/voice -> structured complaint dict.
    The three modality pipelines run CONCURRENTLY (they are independent), which cuts
    mixed-complaint latency from ~3x to ~1x the slowest pipeline."""
    import asyncio

    transcript = ""
    transcript_en = ""
    extracted = None
    vision: Optional[VisionResult] = None
    vision_raw = {}
    photo_path, audio_path = None, None
    photo_meta_data = {}

    async def _voice():
        nonlocal audio_path, transcript
        if not audio_b64:
            return
        audio_path = str(_save_media(audio_b64, audio_ext))
        asr = await ai.transcribe(audio_b64, format_hint=audio_ext, language=language)
        transcript = asr["text"]

    async def _photo():
        nonlocal photo_path, vision, vision_raw, photo_meta_data
        if not image_b64:
            return
        photo_path = str(_save_media(image_b64, "jpg"))
        photo_meta_data = photo_meta.extract_image_metadata(image_b64)
        # apply EXIF orientation so sideways photos are classified correctly
        corrected = _apply_orientation(image_b64, photo_meta_data.get("orientation"))
        vision = await _analyze_photo(corrected or image_b64)
        vision_raw = vision.dict()

    async def _text_extract():
        nonlocal extracted
        # text source: explicit text, else transcript (transcript fills in after voice)
        combined = text.strip()
        if combined:
            extracted = await _extract_text(combined)

    tasks = []
    if audio_b64:
        tasks.append(_voice())
    if image_b64:
        tasks.append(_photo())
    if text.strip():
        tasks.append(_text_extract())
    if tasks:
        await asyncio.gather(*tasks)

    # ---- translation + extraction (single pass for speed) ----
    # The extractor reads Tamil/Hindi/mixed directly and returns an ENGLISH
    # clean_summary — that IS the translation. No separate 20s translate call.
    combined_text = text.strip() or transcript
    if audio_b64 and not transcript and not combined_text and not image_b64:
        # voice note with no recognizable speech and no other modality — ask to repeat
        raise ValueError("Voice note not understood — please speak again or add text/photo.")
    if extracted is None and combined_text:
        extracted = await _extract_text(combined_text)

    if extracted is not None:
        transcript_en = extracted.clean_summary or combined_text
    else:
        transcript_en = combined_text

    # ---- merge policy: max confidence per field ----
    category = extracted.category if extracted else (vision.category if vision else "other")
    # Spam wins if either modality flags it — unrelated content is quarantined.
    is_spam = bool((extracted and extracted.is_spam) or (vision and vision.is_spam))
    if is_spam:
        category = "spam"
    severity = vision.severity if (vision and vision.severity >= 4) else (extracted.severity if extracted else 3)
    severity_reason = []
    if vision:
        severity_reason.append(f"photo: {vision.extent}")
    if extracted:
        severity_reason.append(f"text: {extracted.clean_summary}")
    location_text = extracted.location_text if extracted else (vision.location_text if vision else "")

    # ---- tags: merged union, up to 5 ----
    tags = []
    if extracted and extracted.tags:
        tags.extend(extracted.tags)
    if vision and vision.tags:
        tags.extend(vision.tags)
    seen = set()
    dedup_tags = []
    for t in tags:
        t = str(t).strip().lower().replace(" ", "_")
        if t and t not in seen:
            seen.add(t)
            dedup_tags.append(t)
    tags = dedup_tags[:5]

    # ---- dynamic categories: label from AI, color assigned deterministically ----
    category_label = ""
    if extracted and extracted.category_label:
        category_label = extracted.category_label
    elif vision and vision.category_label:
        category_label = vision.category_label
    if category == "spam":
        category_label = "Spam / Unrelated"
    if not category_label:
        category_label = _DEFAULT_CAT_LABELS.get(category, category.replace("_", " ").title())
    category_color = _assign_category_color(category)

    summary = ""
    if extracted:
        summary = extracted.clean_summary
    if vision and vision.extent and (not summary or (extracted is None) or vision.severity >= (extracted.severity or 3)):
        summary = summary or f"{vision.category}: {vision.extent}"
    if not summary:
        summary = f"{category} reported in Chennai"

    urgent_hint = bool(extracted and extracted.urgent_hint)
    if urgent_hint:
        severity = max(severity, 5)

    # ---- location resolution: GPS share > photo EXIF GPS > text > needs_geo ----
    lat, lng, loc_source, loc_conf = None, None, "needs_geo", "low"
    if gps and gps.get("lat") is not None and gps.get("lng") is not None:
        lat, lng = _sanitize_coords(gps.get("lat"), gps.get("lng"))
        if lat is not None:
            loc_source, loc_conf = "gps", "high"
    elif photo_meta_data.get("lat") is not None:
        lat, lng = _sanitize_coords(photo_meta_data.get("lat"), photo_meta_data.get("lng"))
        if lat is not None:
            loc_source, loc_conf = "photo_exif", "high"
    elif location_text:
        geo = await geocode.geocode_text(location_text)
        if geo:
            lat, lng = geo["lat"], geo["lng"]
            loc_source, loc_conf = "text", "med"

    complaint = {
        "channel": "mix" if sum(bool(x) for x in [text, image_b64, audio_b64]) > 1
        else ("voice" if audio_b64 else ("photo" if image_b64 else "text")),
        "language": language,
        "transcript": transcript,
        "transcript_en": transcript_en,
        "text_raw": text.strip() or transcript,
        "category": category,
        "category_conf": 1.0,
        "category_label": category_label,
        "category_color": category_color,
        "tags": tags,
        "is_spam": is_spam,
        "severity": severity,
        "severity_reason": "; ".join(severity_reason),
        "summary": summary,
        "location_text": location_text,
        "lat": lat, "lng": lng,
        "loc_source": loc_source,
        "loc_confidence": loc_conf,
        "vision_fingerprint": vision.vision_fingerprint if vision else "",
        "vision_raw": vision_raw,
        "photo_meta": photo_meta_data,
        "asr_confidence": None,
        "photo_path": photo_path,
        "audio_path": audio_path,
        "urgent_hint": urgent_hint,
    }
    return complaint
