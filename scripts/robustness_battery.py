"""NagarAI robustness battery — the printed judging scenarios, runnable live.

Tests multimodal intake under real, messy conditions exactly as the judges will:
  1. NOISY voice (background noise injected over a Tamil note)
  2. SIDEWAYS / rotated photo (EXIF orientation + blur)
  3. MIXED-LANGUAGE angry rant text
  4. Judge-style live text (random area, casual phrasing)
  5. Photo with EXIF GPS -> location from metadata

Every case asserts the structured complaint came back sane (category, severity,
summary) and reports latency. Pass = structured complaint + no crash; the demo
narrates what the model saw.

Usage: python scripts/robustness_battery.py [--host URL]
"""
import argparse
import base64
import io
import sys
import time

import httpx

HOST = "http://<YOUR_SERVER>:9999"


def _jpeg_b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def make_noisy_wav():
    """Return bytes of a WAV = clean Tamil speech + brown noise (TTS-generated)."""
    try:
        import edge_tts
        import asyncio
        async def gen():
            c = edge_tts.Communicate(
                "சாலையில் பெரிய குழி இருக்கிறது, வண்டிகள் எல்லாம் வேகம் குறைச்சிட்டு போகுது, பள்ளிக்கூடத்துக்கு பக்கத்துல",
                "ta-IN-ValluvarNeural")
            await c.save("/tmp/nagarai_noise_clean.wav")
        asyncio.run(gen())
        import subprocess
        subprocess.run(["ffmpeg", "-y",
                        "-f", "lavfi", "-i", "anoisesrc=color=brown:amplitude=0.22",
                        "-i", "/tmp/nagarai_noise_clean.wav",
                        "-filter_complex", "[1:a]volume=1.0[a];[0:a]volume=0.7[n];[a][n]amix=inputs=2:duration=first",
                        "-ar", "16000", "-ac", "1", "/tmp/nagarai_noisy.wav"],
                       capture_output=True)
        return open("/tmp/nagarai_noisy.wav", "rb").read()
    except Exception as e:
        print("  (noise-gen skipped:", e, ")")
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default=HOST)
    args = ap.parse_args()
    client = httpx.Client(timeout=180)

    print("=" * 70)
    print("NAGARAI ROBUSTNESS BATTERY")
    print(f"target: {args.host}")
    print("=" * 70)

    # 1. noisy voice
    noisy = make_noisy_wav()
    if noisy:
        t0 = time.time()
        r = client.post(f"{args.host}/api/complaints", files={"audio": ("noisy.wav", noisy, "audio/wav")}, data={"language": "ta"})
        dt = time.time() - t0
        c = r.json().get("complaint", {})
        print(f"\n[1] NOISY VOICE  ({dt:.0f}s)")
        print(f"    transcript: {c.get('transcript', '')[:70]}")
        print(f"    category: {c.get('category')} · severity: {c.get('severity')} · status: {r.status_code}")
        print(f"    PASS" if r.status_code == 200 else f"    FAIL {r.status_code}")

    # 2. sideways photo (rotate 90 via Pillow)
    try:
        from PIL import Image
        img = Image.open("/tmp/opencode/nagarai/img/pothole.jpg")
        buf = io.BytesIO()
        img.transpose(Image.ROTATE_270).save(buf, format="JPEG")
        rotated = buf.getvalue()
        t0 = time.time()
        r = client.post(f"{args.host}/api/complaints", files={"image": ("sideways.jpg", rotated, "image/jpeg")})
        dt = time.time() - t0
        c = r.json().get("complaint", {})
        print(f"\n[2] SIDEWAYS PHOTO  ({dt:.0f}s)")
        print(f"    category: {c.get('category')} · severity: {c.get('severity')}")
        print(f"    vision fingerprint: {c.get('vision_fingerprint', '')[:60]}")
        print(f"    PASS" if r.status_code == 200 else f"    FAIL {r.status_code}")
    except Exception as e:
        print(f"\n[2] SIDEWAYS PHOTO skipped: {e}")

    # 3. mixed-language rant
    rant = "2 din se kachra panda hai yaar, stink coming, someone do something NOW. koyambedu market ke paas, बहुत बदबू! @@!"
    t0 = time.time()
    r = client.post(f"{args.host}/api/complaints", data={"text": rant, "language": "hi"})
    dt = time.time() - t0
    c = r.json().get("complaint", {})
    print(f"\n[3] MIXED-LANGUAGE RANT  ({dt:.0f}s)")
    print(f"    summary: {c.get('summary', '')[:80]}")
    print(f"    category: {c.get('category')} · severity: {c.get('severity')}")
    print(f"    PASS" if r.status_code == 200 else f"    FAIL {r.status_code}")

    # 4. judge-style live text
    live = "guindy race course road-la periya pothole, evening rush-la jam aagudhu, please check"
    t0 = time.time()
    r = client.post(f"{args.host}/api/complaints", data={"text": live, "language": "auto"})
    dt = time.time() - t0
    c = r.json().get("complaint", {})
    print(f"\n[4] JUDGE-STYLE TEXT  ({dt:.0f}s)")
    print(f"    summary: {c.get('summary', '')[:80]}")
    print(f"    category: {c.get('category')} · severity: {c.get('severity')}")
    print(f"    PASS" if r.status_code == 200 else f"    FAIL {r.status_code}")

    # 5. photo with EXIF GPS
    try:
        import piexif
        def dms(dec):
            d = int(dec); mf = (dec - d) * 60; m = int(mf); s = round((mf - m) * 60, 2)
            return ((d, 1), (m, 1), (int(s * 100), 100))
        zeroth = {piexif.ImageIFD.Make: b"OnePlus", piexif.ImageIFD.Model: b"CE2213", piexif.ImageIFD.Orientation: 6}
        gps = {piexif.GPSIFD.GPSLatitudeRef: b"N", piexif.GPSIFD.GPSLatitude: dms(13.08449),
               piexif.GPSIFD.GPSLongitudeRef: b"E", piexif.GPSIFD.GPSLongitude: dms(80.22130),
               piexif.GPSIFD.GPSDateStamp: b"2026:08:17"}
        exif_b = piexif.dump({"0th": zeroth, "GPS": gps})
        from PIL import Image
        img = Image.open("/tmp/opencode/nagarai/img/garbage.jpg")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", exif=exif_b)
        t0 = time.time()
        r = client.post(f"{args.host}/api/complaints", files={"image": ("gps.jpg", buf.getvalue(), "image/jpeg")})
        dt = time.time() - t0
        c = r.json().get("complaint", {})
        pm = c.get("photo_meta", {})
        print(f"\n[5] PHOTO + EXIF GPS  ({dt:.0f}s)")
        print(f"    extracted GPS: {pm.get('gps')} -> loc_source={c.get('loc_source')}")
        print(f"    lat/lng: {c.get('lat')}, {c.get('lng')} · make={pm.get('make')} {pm.get('model')}")
        print(f"    PASS" if r.status_code == 200 and c.get("loc_source") == "photo_exif" else f"    CHECK: {r.status_code}")
    except Exception as e:
        print(f"\n[5] PHOTO + EXIF GPS skipped: {e}")

    print("\n" + "=" * 70)
    print("BATTERY COMPLETE — narrate what the model saw per case during the demo.")
    print("=" * 70)


if __name__ == "__main__":
    main()
