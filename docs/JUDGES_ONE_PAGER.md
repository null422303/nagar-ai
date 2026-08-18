# NAGAR AI — Ward Control Room
### Civic Complaint Intelligence Engine · PS-S05 · One-Page Snapshot

**Live demo:** `<YOUR_DEMO_URL>` · **Admin password:** `<ADMIN_PASSWORD>`

---

## What it is
Citizens file complaints in **Tamil / Hindi / English (voice · photo · text — any mix)**.
The AI extracts one structured complaint, **deduplicates** against live clusters,
**prioritises** with a transparent formula, and shows officials a **ranked ward map**.

## The 30-second demo flow
1. **Citizen files** a messy complaint → structured receipt (ticket ID, category, severity, location, summary).
2. **Dedup** — duplicates auto-merge into one issue with a "why merged" audit trail.
3. **Priority (PRT)** — every card shows the formula terms (band · P · T · L).
4. **Official acts** — Assign → In progress → Resolve.
5. **Citizen tracks** by ticket ID → progress bar.

## Judging criteria → how we score

| Criterion | Weight | Delivered |
|---|---|---|
| Deduplication quality | 30% | **purity 1.0 · coverage 1.0 · merge accuracy 1.0** (15-complaint set → exactly 5 issues) |
| Multimodal intake robustness | 25% | noisy Tamil voice (thanglish verbatim), photo-only upload, mixed-language rant, EXIF GPS — **5/5 robustness battery PASS** |
| Explainable prioritisation | 20% | severity-band PRT formula, every term on-screen, worked example |
| Official dashboard utility | 15% | map + filters + cluster cards + one-click status + SLA |
| End-to-end completeness | 10% | full loop live: file → dedup → priority → resolve → track |

## Key original work
- **Canonicalize-then-embed dedup** — DashScope embeddings are weak on Tamil (validated:
  garbage EN↔TA cos=0.24 < pothole-vs-garbage 0.32), so complaints are first normalised into
  an English *issue fingerprint* and embedded once; clustering blends text + geo(60m) + vision.
- **Severity-band priority** — a 40-complaint pothole can never outrank a 2-complaint live-wire
  (S≥5 hazards auto-rank 90–99; within bands rank = P·T·L, log-damped & gamed-resistant).
- **Dynamic AI categories** — when an issue doesn't fit the 4 standard types, the model creates
  a new category + label + colour (e.g. `stray_dogs` → "Stray Dog Menace", #FF5A1F).
- **Exact photo EXIF** — cm-level GPS + DMS, sub-second capture time, camera, altitude, heading;
  photo-EXIF GPS is a first-class location source (also auto-locates via browser GPS and vision signage).
- **Tickets** — every complaint has an ID; status chain Open → Assigned → In Progress → Resolved.

## Stack
FastAPI (Python) · OpenRouter voxtral ASR · DashScope qwen3.7-flash / qwen-vl / embeddings ·
piexif EXIF · Leaflet map · CSV storage · self-hosted Ward Control Room UI · HTTPS via Caddy/sslip.io

## Honest limitations
- ASR is API-based (voxtral); heavy noise can trigger a graceful "please repeat" — never fake output.
- No local models — full offline is a demo fallback (clearly marked OFFLINE DEMO).
- 1-core server, CSV storage: built for hackathon scale.
