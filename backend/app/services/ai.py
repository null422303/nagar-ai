"""HTTP client for DashScope + OpenRouter with response caching.

Every API call goes through here. Responses are cached by (model, request_hash)
in a CSV file so the 15-complaint set + demo replay costs nothing extra.
"""
import base64
import hashlib
import json
import os
import subprocess
import tempfile
import time
from typing import Optional

import httpx
from app.core.config import settings

_TIMEOUT = httpx.Timeout(300.0, connect=30.0)


def _get_ffmpeg() -> Optional[str]:
    """Locate a usable ffmpeg (system or imageio static binary)."""
    import shutil
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None


def _to_wav_16k(base64_audio: str, ext: str) -> str:
    """Convert any audio (webm/opus/ogg/mp4) to 16kHz mono WAV for the ASR provider.
    Applies sensitivity preprocessing: highpass removes low rumble, volume boosts
    quiet recordings, limiter prevents clipping. Returns base64 WAV; falls back to
    the original bytes if conversion is unavailable."""
    ffmpeg = _get_ffmpeg()
    if not ffmpeg:
        return base64_audio
    try:
        raw = base64.b64decode(base64_audio)
        with tempfile.NamedTemporaryFile(suffix="." + ext, delete=False) as fin:
            fin.write(raw)
            in_path = fin.name
        out_path = in_path + ".wav"
        r = subprocess.run(
            [ffmpeg, "-y", "-i", in_path, "-ar", "16000", "-ac", "1",
             "-af", "highpass=f=80,volume=2.0,alimiter=limit=0.95", out_path],
            capture_output=True, timeout=300,
        )
        if r.returncode == 0:
            with open(out_path, "rb") as f:
                out_b64 = base64.b64encode(f.read()).decode()
            return out_b64
    except Exception:
        pass
    finally:
        for p in (in_path, out_path):
            try:
                os.unlink(p)
            except Exception:
                pass
    return base64_audio


# voxtral reliably hears ~30s per request; keep a safety margin and stitch longer
# clips by splitting with a small overlap so no word is cut at a boundary.
_MAX_ASR_SEGMENT_S = 26.0
_ASR_OVERLAP_S = 1.5


def _wav_seconds(wav_b64: str) -> float:
    """Duration of a 16kHz-mono-16-bit WAV (base64) in seconds."""
    try:
        return len(base64.b64decode(wav_b64)) / 32000.0
    except Exception:
        return 0.0


def _split_wav_segments(wav_b64: str, seg_s: float = _MAX_ASR_SEGMENT_S,
                        overlap_s: float = _ASR_OVERLAP_S) -> list:
    """Split a 16kHz-mono-16-bit WAV (base64) into <=seg_s chunks with overlap.
    Returns a list of base64 WAV segment strings. Single segment if already short."""
    total = _wav_seconds(wav_b64)
    if total <= seg_s or total <= 0:
        return [wav_b64]
    ffmpeg = _get_ffmpeg()
    if not ffmpeg:
        return [wav_b64]
    out = []
    try:
        raw = base64.b64decode(wav_b64)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as fin:
            fin.write(raw)
            in_path = fin.name
        start = 0.0
        idx = 0
        while start < total - 0.1:
            out_path = f"{in_path}.seg{idx}.wav"
            r = subprocess.run(
                [ffmpeg, "-y", "-i", in_path, "-ss", f"{start:.2f}", "-t", f"{seg_s:.2f}",
                 "-ar", "16000", "-ac", "1", out_path],
                capture_output=True, timeout=300)
            if r.returncode != 0 or not os.path.exists(out_path):
                break
            with open(out_path, "rb") as f:
                out.append(base64.b64encode(f.read()).decode())
            os.unlink(out_path)
            idx += 1
            start += seg_s - overlap_s
    except Exception:
        out = [wav_b64]
    finally:
        try:
            os.unlink(in_path)
        except Exception:
            pass
    return out or [wav_b64]


def _req_hash(model: str, payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(f"{model}::{raw}".encode()).hexdigest()


class Cache:
    _rows: Optional[dict] = None
    _path = settings.CACHE_CSV  # csv file path
    _loaded = False

    @classmethod
    def _load(cls) -> None:
        if cls._loaded:
            return
        cls._rows = {}
        if cls._path.exists():
            import csv
            with open(cls._path, newline="", encoding="utf-8") as f:
                for row in csv.DictReader(f):
                    cls._rows[row["h"]] = row
        cls._loaded = True

    @classmethod
    def get(cls, model: str, payload: dict) -> Optional[dict]:
        cls._load()
        h = _req_hash(model, payload)
        row = cls._rows.get(h)
        if row:
            return json.loads(row["body"])
        return None

    @classmethod
    def put(cls, model: str, payload: dict, body: dict) -> None:
        cls._load()
        h = _req_hash(model, payload)
        cls._rows[h] = {"h": h, "model": model,
                        "body": json.dumps(body, ensure_ascii=False),
                        "ts": time.time()}
        import csv
        cls._path.parent.mkdir(parents=True, exist_ok=True)
        with open(cls._path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=["h", "model", "body", "ts"])
            w.writeheader()
            for row in cls._rows.values():
                w.writerow(row)

    @classmethod
    def size(cls) -> int:
        cls._load()
        return len(cls._rows)


async def _post(url: str, headers: dict, payload: dict, model: str, use_cache: bool = True) -> dict:
    if use_cache:
        hit = Cache.get(model, payload)
        if hit:
            return hit
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        r = await client.post(url, headers=headers, json=payload)
    if r.status_code >= 400:
        raise RuntimeError(f"{model} HTTP {r.status_code}: {r.text[:400]}")
    body = r.json()
    if use_cache:
        Cache.put(model, payload, body)
    return body


# ---------- DashScope multi-key round-robin with retry ----------
_DS_KEYS = list(settings.DASHSCOPE_API_KEYS)
_ds_round = 0  # round-robin cursor (module-level, shared across requests)


def _next_ds_key() -> str:
    global _ds_round
    if not _DS_KEYS:
        return ""
    key = _DS_KEYS[_ds_round % len(_DS_KEYS)]
    _ds_round += 1
    return key


def _is_quota_error(status: int, body: dict) -> bool:
    """A key is unusable (quota / auth / rate / exhausted) — rotate away from it."""
    if status in (401, 403, 429):
        return True
    if status >= 500:
        return False  # server-side errors are not the key's fault
    code = str((body or {}).get("error", {}).get("code", "")).lower()
    msg = str((body or {}).get("error", {}).get("message", "")).lower()
    if any(k in code + msg for k in ("quota", "rate", "free_tier", "allocation",
                                     "exhaust", "invalid_api_key", "invalid api key",
                                     "access denied", "unauthorized", "permission")):
        return True
    return False


async def _dashscope_post(url: str, payload: dict, model: str, use_cache: bool = True,
                          max_rotations: int = 3) -> dict:
    """POST to DashScope, rotating keys on quota/5xx errors (round-robin + retry)."""
    if use_cache:
        hit = Cache.get(model, payload)
        if hit:
            return hit

    n = max(len(_DS_KEYS), 1)
    for _ in range(n * max_rotations):
        key = _next_ds_key()
        if not key:
            break
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
                r = await client.post(url, headers=headers, json=payload)
            if r.status_code < 400:
                body = r.json()
                if use_cache:
                    Cache.put(model, payload, body)
                return body
            try:
                err_body = r.json()
            except Exception:
                err_body = {}
            if _is_quota_error(r.status_code, err_body):
                # move this key to the back of the rotation + reset cursor
                if key in _DS_KEYS:
                    _DS_KEYS.remove(key)
                    _DS_KEYS.append(key)
                _ds_round = 0
                continue  # try the next key
            raise RuntimeError(f"{model} HTTP {r.status_code}: {r.text[:400]}")
        except (httpx.TimeoutException, httpx.ConnectError):
            # transient network failure — rotate + retry once
            if key in _DS_KEYS:
                _DS_KEYS.remove(key)
                _DS_KEYS.append(key)
            _ds_round = 0
            continue

    # all keys failed on quota — surface a clear error
    raise RuntimeError(f"{model}: all DashScope keys exhausted/out of quota ({len(_DS_KEYS)} keys)")


async def chat(prompt: str, model: Optional[str] = None, system: Optional[str] = None,
               json_mode: bool = False, max_tokens: int = 600, use_cache: bool = True,
               images: Optional[list] = None) -> str:
    """DashScope chat (text or multimodal with images). images = list of data-URI strings."""
    model = model or settings.MODEL_TEXT
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    content = prompt if images is None else [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": img}} for img in images
    ]
    msgs.append({"role": "user", "content": content})
    payload = {"model": model, "messages": msgs, "max_tokens": max_tokens}
    # qwen3.7-flash/qwen-vl-max reason by default; disable thinking for latency
    # (extraction/vision calls dropped from ~14s to ~2s). OpenRouter ASR is separate.
    payload["enable_thinking"] = False
    if json_mode:
        payload["response_format"] = {"type": "json_object"}
    body = await _dashscope_post(f"{settings.DASHSCOPE_BASE_URL}/chat/completions",
                                  payload, model, use_cache)
    return body["choices"][0]["message"]["content"]


async def embed(texts: list, model: Optional[str] = None) -> list:
    """DashScope embeddings. Returns list of float vectors."""
    model = model or settings.MODEL_EMBED
    payload = {"model": model, "input": texts}
    body = await _dashscope_post(f"{settings.DASHSCOPE_BASE_URL}/embeddings",
                                 payload, model, use_cache=True)
    return [m["embedding"] for m in body["data"]]


async def _asr_call(payload: dict, use_cache: bool = True) -> str:
    body = await _post("https://openrouter.ai/api/v1/chat/completions",
                       {"Authorization": f"Bearer {settings.OPENROUTER_API_KEY}", "Content-Type": "application/json"},
                       payload, settings.MODEL_ASR, use_cache)
    return body["choices"][0]["message"]["content"].strip()


def _clean_transcript(content: str) -> str:
    return content.split("\n")[0].strip().strip('"')


async def _transcribe_wav(wav_b64: str, language: str = "") -> dict:
    """Transcribe a single WAV segment (<= ~26s). Auto language uses the fast
    verbatim path; explicit ta/hi/en uses a script-forcing prompt."""
    lang = (language or "").strip().lower()
    if lang in ("auto", "auto-detect", ""):
        return await _transcribe_auto(wav_b64)
    script_instr = {
        "ta": "Output the transcription in Tamil script (தமிழ் எழுத்துக்கள்), verbatim.",
        "hi": "Output the transcription in Devanagari script (हिन्दी), verbatim.",
        "en": "Output the transcription in English, verbatim.",
    }.get(lang, "Output the transcription verbatim, preserving the original language and script.")
    sysp = ("You are an ASR engine. Transcribe ONLY the speech as heard, verbatim. "
            "Never translate, never fix, never comment, never add words you did not hear."
            f" The spoken language is {lang}." + " " + script_instr +
            " If you cannot understand the speech, output exactly: [UNCLEAR]")
    payload = {
        "model": settings.MODEL_ASR,
        "messages": [{"role": "system", "content": sysp},
                     {"role": "user", "content": [
                         {"type": "text", "text": "Transcribe"},
                         {"type": "input_audio", "input_audio": {"data": wav_b64, "format": "wav"}},
                     ]}],
        "max_tokens": 1600,
    }
    for attempt in range(3):
        content = await _asr_call(payload)
        text = _clean_transcript(content)
        if text and "[UNCLEAR]" not in content:
            return {"text": text, "confidence": 1.0}
    return {"text": "", "confidence": 0.0}


async def transcribe(base64_audio: str, format_hint: str = "wav", language: str = "") -> dict:
    """OpenRouter voxtral ASR. Accepts wav/mp3/webm/ogg/opus/mp4 (webm/ogg converted to
    16kHz mono wav via bundled ffmpeg with gain boost). Clips longer than ~26s are
    split into overlapping segments, transcribed separately and stitched, so voice
    notes of any length are heard in full.

    language strategy (explicit-first, reliable):
      - ta/hi/en chosen  -> strong script-forcing prompt (deterministic, tested)
      - auto / ""         -> fast single-pass verbatim per segment
    """
    ext = (format_hint or "wav").lower().lstrip(".")
    if ext in ("webm", "ogg", "opus", "mp4", "m4a", "aac", "mpeg"):
        base64_audio = _to_wav_16k(base64_audio, ext)
        format_hint = "wav"

    segments = _split_wav_segments(base64_audio)
    if len(segments) <= 1:
        return await _transcribe_wav(base64_audio, language)

    parts = []
    for i, seg in enumerate(segments):
        r = await _transcribe_wav(seg, language)
        t = (r or {}).get("text", "")
        if t:
            parts.append(t)
    stitched = " ".join(parts).strip()
    return {"text": stitched, "confidence": 1.0 if stitched else 0.0}


async def _transcribe_auto(base64_audio: str, format_hint: str = "wav") -> dict:
    """Auto language — single-pass for speed: transcribe verbatim in the speaker's
    NATIVE script (Tamil → தமிழ், Hindi → हिन्दी, Kannada → ಕನ್ನಡ, English stays Latin).
    Never output romanized/thanglish. Only if that returns empty do we retry."""
    # Pass 1: fast verbatim transcription (minimal prompt is reliable + fast)
    sysp = ("Transcribe the audio verbatim in the speaker's NATIVE script. "
            "Tamil speech MUST be Tamil script (தமிழ்), Hindi speech MUST be Devanagari "
            "(हिन्दी), Kannada MUST be Kannada script (ಕನ್ನಡ), Telugu MUST be Telugu script "
            "(తెలుగు). NEVER transliterate to Roman/English letters. If the speech is "
            "already English, output English. Output only the transcription. "
            "If unclear output [UNCLEAR].")
    payload = {
        "model": settings.MODEL_ASR,
        "messages": [{"role": "system", "content": sysp},
                     {"role": "user", "content": [
                         {"type": "text", "text": "Transcribe"},
                         {"type": "input_audio", "input_audio": {"data": base64_audio, "format": format_hint}},
                     ]}],
        "max_tokens": 1600,
    }
    for _ in range(3):
        content = await _asr_call(payload, use_cache=False)
        text = _clean_transcript(content)
        if text and "[UNCLEAR]" not in content:
            return {"text": text, "confidence": 1.0}
    # Pass 2 (rare): detect language, then explicit script prompt
    detect_sysp = ("You are a language detector. From the audio, output ONLY the language tag: "
                   "ta, hi, en, or mixed. Nothing else.")
    detect_payload = {
        "model": settings.MODEL_ASR,
        "messages": [{"role": "system", "content": detect_sysp},
                     {"role": "user", "content": [
                         {"type": "text", "text": "Detect the language"},
                         {"type": "input_audio", "input_audio": {"data": base64_audio, "format": format_hint}},
                     ]}],
        "max_tokens": 10,
    }
    detected = ""
    try:
        content = await _asr_call(detect_payload, use_cache=False)
        detected = _clean_transcript(content).lower().strip(".")
    except Exception:
        detected = ""
    if detected in ("ta", "hi", "en"):
        return await transcribe(base64_audio, format_hint, language=detected)
    return {"text": "", "confidence": 0.0}
