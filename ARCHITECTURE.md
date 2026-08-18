# NagarAI — Architecture

## Overview
NagarAI is a civic complaint intelligence engine: citizens file voice/photo/text complaints
(Tamil, Hindi, English, any mix); the system extracts structured complaints, deduplicates them
into live issues, scores them with a transparent priority formula, and shows officials a mapped,
ranked ward control room.

## System flow
```
Citizen (Ward Control Room UI)
  voice(live Web Speech API) · photo(EXIF) · text(any language)
    │  live browser ASR · qwen-vl vision · qwen3.7-flash extraction · piexif EXIF
    ▼
Structured complaint {category, label, color, severity, summary, location, photo_meta}
    ▼  Dedup: canonicalize-then-embed + geo(60m) + vision → online clustering
Issue {affected_count, per-merge audit trail}
    ▼  Priority: band(S) · P(affected) · T(days) · L(proximity) — formula visible
Admin map/board → resolve → citizen track status
```

## Key components
| Layer | Files | Role |
|---|---|---|
| API | `backend/app/api/routes.py` | `/complaints`, `/asr`, `/issues`, `/status`, `/search`, `/stats`, `/recent`, `/reset`, `/health` |
| Intake | `backend/app/services/intake.py` | voice/photo/text → one structured complaint; dynamic AI categories |
| Dedup | `backend/app/engines/dedup.py` | canonicalize-then-embed, geo-fenced online clustering, SLA routing |
| Priority | `backend/app/engines/priority.py` | severity-band formula (band(S)·P·T·L) |
| AI clients | `backend/app/services/ai.py` | DashScope + OpenRouter, CSV response cache, webm→wav |
| Geocode | `backend/app/services/geocode.py` | Nominatim/Overpass with retry + POI cache |
| Photo meta | `backend/app/services/photo_meta.py` | exact EXIF (GPS, camera, time, altitude, heading) |
| Storage | `backend/app/models/store.py` | CSV tables (complaints, issues, memberships, poi) |
| Frontend | `frontend/site/` | self-hosted Ward Control Room (3 views), no build step |

## Ports & URLs
- **Backend listens on `:9999`** (internal). Serve the app on 80/443 via a reverse proxy
  (Caddy). The public URL carries no port.
- HTTPS is required for browser mic + geolocation (secure context).
- A trusted HTTPS URL can be obtained via a domain or a wildcard DNS service (e.g. sslip.io)
  with Caddy auto-provisioning a Let's Encrypt certificate.

## Deployment
`scripts/deploy.sh` syncs code + installs deps + starts uvicorn on `:9999`.
Credentials are read from env (see README's "where to change" table).
