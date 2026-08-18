# NagarAI — Technical Note (one page)

## What was built
NagarAI is a civic-complaint intelligence engine: citizens file voice/photo/text complaints in
9 Indian languages; the system extracts one structured complaint `{category, location, severity,
one-line summary}`, deduplicates it against a live issue map, scores it with a transparent formula
(PRT), and shows officials a ranked Ward Control Room dashboard. Photo EXIF gives exact geotags;
voice is transcribed **live in the browser** via the Web Speech API in the speaker's native script.

## Models & endpoints used (all API — no local ML)
| Component | Model | Provider |
|---|---|---|
| Live voice transcription | Browser **Web Speech API** (client-side) | browser, 9 Indian languages |
| Optional server ASR | `mistralai/voxtral-small-24b-2507` | OpenRouter (`/api/asr`) |
| Photo classification + severity | `qwen-vl-max` | DashScope compatible-mode |
| Text extraction / canonicalization | `qwen3.7-flash` | DashScope compatible-mode |
| Dedup embeddings | `qwen3.7-text-embedding` | DashScope compatible-mode |
| Geocoding / POIs | Nominatim + Overpass (OSM) | free, cached in CSV |
| Photo EXIF | piexif / Pillow | local, exact metadata |
| Audio convert (webm→wav) | imageio-ffmpeg static binary | local |

## Original work
- **Canonicalize-then-embed dedup**: raw DashScope embeddings are weak on Tamil (validated: garbage
  EN↔TA cos = 0.24, *below* the pothole-vs-garbage cross distance 0.32). Every complaint is first
  normalized into an English *issue fingerprint* (`category | location | vision | summary`), embedded
  once, then clustered online with `sim = 0.55·text + 0.30·geo(60m) + 0.15·vision`, geo-fenced at 500m,
  adaptive weights when a signal is missing/geocode is uninformative. Every merge stores its 3 scores.
- **Severity-band priority formula (PRT)**: `band(S)` master gate — S≥5 hazards auto-rank 90–99; within
  bands, `rank = P(affected, log-damped) × T(days, saturating) × L(proximity ×1.5)`. A 40-complaint
  pothole (~80) can never outrank a 2-complaint live-wire (~90).
- **Location sources**: GPS share > **photo EXIF GPS** (`photo_exif`) > vision signage > text geocode >
  needs-geo pool. EXIF extraction returns exact make/model, capture time, GPS DMS→decimal, altitude,
  orientation; the photo is auto-rotated per orientation before vision classification. The vision model
  also reads street signs/landmarks from the photo (`location_text`) so photo-only submissions auto-locate.
- **Photo-only intake**: uploading a photo alone is enough — vision classifies the issue (and creates a
  new AI category if needed), no text description required.
- **Robustness engineering**: live voice streams interim results (no server round-trip); the
  backend extractor reads Tamil/Hindi/English/code-mixed text directly and normalizes it.
  Geocoder normalizes "Second Avenue"→"2nd" with retry/backoff. Every API call cached (re-runs ~free).
- **Speed**: `enable_thinking:false` on DashScope chat cuts extraction/vision from ~14s to ~2s (full
  complaint ~25s → ~4s). Live voice is instant. DashScope calls round-robin across multiple API keys
  with auto-retry on quota/5xx.

## Results (synthetic 15-complaint bench, live on production)
Purity **1.0** · coverage **1.0** · merge accuracy **1.0** · category accuracy **1.0**.
15 complaints → exactly 5 issues (two nearby pothole clusters correctly kept separate).

## Robustness battery (live, passes)
Noisy Tamil voice · sideways photo · mixed-language rant · judge-style text · photo+EXIF GPS —
all return sane structured complaints.

## Known failure modes (honest)
- **Live voice depends on the browser's Web Speech API**: quality varies by browser/OS; heavy
  noise may yield a partial transcript (editable in the box before submit). Optional server
  voxtral ASR (`/api/asr`) covers browsers without Web Speech API.
- **Vision on ambiguous/synthetic photos** may return `other`; real judge photos expected stronger.
- **Nominatim rate-limits**: retry+backoff; frequent filings may hit the "needs-geo" pool.
- **No local model / full offline**: API-first by design (24h build, no GPU); documented limitation.
- **CSV storage**: fine for hackathon scale; lock-protected, not sharded.
- Budget: expected ~$1–5 total (cached; cheapest competent model per task).

## Team conduct
All code written during the event. Open source: everything in-repo. No unsafe hardware work.
