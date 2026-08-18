"""Photo metadata extraction — exact EXIF from uploaded images.

Extracts: GPS (lat/lng + refs), capture timestamp, camera make/model, and
orientation. GPS is converted from DMS -> decimal degrees. Used for the
'photo metadata' location source and for the dedup/priority pipeline.

All values are typed (float lat/lng, ISO timestamps, strings) so the UI can
display exact metadata.
"""
import base64
import io
from typing import Optional

try:
    import piexif
    HAS_PIEXIF = True
except Exception:
    HAS_PIEXIF = False


def _dms_to_decimal(dms, ref, precision: int = 9) -> Optional[float]:
    """Convert EXIF DMS (degrees, minutes, seconds as (num,den) rationals) to decimal degrees.
    precision=9 gives ~0.1mm — exact, not rounded away."""
    try:
        if not dms or len(dms) < 3:
            return None
        def _r(x):
            if isinstance(x, (tuple, list)):
                return float(x[0]) / float(x[1]) if x[1] else 0.0
            return float(x)
        dec = _r(dms[0]) + _r(dms[1]) / 60.0 + _r(dms[2]) / 3600.0
        if ref in (b"S", b"s", "S", "s"):
            dec = -dec
        if ref in (b"W", b"w", "W", "w"):
            dec = -dec
        return round(dec, precision)
    except Exception:
        return None


def _rat_float(v):
    """EXIF rational (num,den) or int -> float."""
    if v is None:
        return None
    try:
        if isinstance(v, (tuple, list)):
            return float(v[0]) / float(v[1]) if len(v) == 2 and v[1] else None
        return float(v)
    except Exception:
        return None


def _gps_precise(lat, lng) -> str:
    """Human-readable exact DMS from decimal, e.g. 13°05'04.88"N 80°13'16.68"E."""
    def fmt(dec, pos, neg):
        hemi = pos if dec >= 0 else neg
        d = abs(dec)
        deg = int(d)
        mf = (d - deg) * 60
        mi = int(mf)
        sec = (mf - mi) * 60
        return "{0}\u00b0{1:02d}'{2:05.2f}\"{3}".format(deg, mi, sec, hemi)
    return fmt(lat, "N", "S") + " " + fmt(lng, "E", "W")


def extract_image_metadata(image_b64: str) -> dict:
    """Return exact EXIF metadata dict. Empty dict if no EXIF / parse fails."""
    if not HAS_PIEXIF:
        return {}
    try:
        raw = base64.b64decode(image_b64)
        exif_bytes = piexif.load(raw)
    except Exception:
        return {}

    zeroth = exif_bytes.get("0th", {})
    exif_ifd = exif_bytes.get("Exif", {})
    gps = exif_bytes.get("GPS", {})
    ifd1 = exif_bytes.get("1st", {})

    meta = {}
    II = piexif.ImageIFD
    EI = piexif.ExifIFD
    GI = piexif.GPSIFD

    # camera
    for tag, key in ((II.Make, "make"), (II.Model, "model"),
                     (II.Software, "software"), (II.Orientation, "orientation")):
        val = zeroth.get(tag)
        if isinstance(val, bytes):
            meta[key] = val.decode("utf-8", "ignore").strip() or None
        elif val is not None:
            meta[key] = val

    # capture time (DateTimeOriginal preferred, then DateTimeDigitized, then DateTime)
    dt = exif_ifd.get(EI.DateTimeOriginal) or exif_ifd.get(EI.DateTimeDigitized) or zeroth.get(II.DateTime)
    if isinstance(dt, bytes):
        dt = dt.decode("utf-8", "ignore")
    if dt:
        try:
            # "YYYY:MM:DD HH:MM:SS" -> ISO
            meta["captured_at"] = dt.replace(":", "-", 2).replace(" ", "T")
        except Exception:
            meta["captured_at"] = str(dt)

    # exposure / focal for "exactness" when present
    for tag, key in ((EI.FNumber, "fnumber"), (EI.ExposureTime, "exposure"),
                     (EI.FocalLength, "focal_length"), (EI.ISOSpeedRatings, "iso"),
                     (EI.FocalLengthIn35mmFilm, "focal_35mm")):
        val = exif_ifd.get(tag)
        if val is not None:
            meta[key] = str(val)

    # GPS — full precision
    lat_ref = gps.get(GI.GPSLatitudeRef)
    lng_ref = gps.get(GI.GPSLongitudeRef)
    lat = _dms_to_decimal(gps.get(GI.GPSLatitude), lat_ref)
    lng = _dms_to_decimal(gps.get(GI.GPSLongitude), lng_ref)
    if lat is not None and lng is not None:
        meta["gps"] = {
            "lat": lat, "lng": lng,
            "lat_ref": lat_ref.decode() if isinstance(lat_ref, bytes) else lat_ref,
            "lng_ref": lng_ref.decode() if isinstance(lng_ref, bytes) else lng_ref,
            "dms": _gps_precise(lat, lng),
            "precision_m": _rat_float(gps.get(GI.GPSHPositioningError)),
        }
        meta["lat"] = lat
        meta["lng"] = lng

        # GPS date + time-of-day for exact capture instant
        gps_date = gps.get(GI.GPSDateStamp)
        gps_time = gps.get(GI.GPSTimeStamp)
        if isinstance(gps_date, bytes):
            gps_date = gps_date.decode("utf-8", "ignore")
        if gps_time:
            t = [_rat_float(x) for x in gps_time][:3]
            if gps_date and t and all(x is not None for x in t):
                hh, mm = int(t[0]), int(t[1])
                ss = t[2]
                meta["gps_instant"] = f"{gps_date} {hh:02d}:{mm:02d}:{ss:06.3f}Z"
        if gps_date:
            meta["gps_date"] = gps_date

    alt = gps.get(GI.GPSAltitude)
    if alt is not None:
        v = _rat_float(alt)
        if v is not None:
            meta["altitude_m"] = round(v, 2)
    alt_ref = gps.get(GI.GPSAltitudeRef)
    if alt_ref is not None:
        meta["altitude_ref"] = "below" if alt_ref == 1 else "above"

    for tag, key in ((GI.GPSTrack, "heading_deg"), (GI.GPSSpeed, "speed_kmh")):
        v = _rat_float(gps.get(tag))
        if v is not None:
            meta[key] = round(v, 2)
    img_dir = gps.get(GI.GPSImgDirection)
    if img_dir is not None:
        v = _rat_float(img_dir)
        if v is not None:
            meta["image_direction_deg"] = round(v, 2)

    if meta.get("gps"):
        # optional place label resolved downstream (intake → geocode) for map display
        pass

    return meta


def has_gps(image_b64: str) -> bool:
    meta = extract_image_metadata(image_b64)
    return bool(meta.get("gps"))
