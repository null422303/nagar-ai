# NagarAI Live Demo Script (judging order)

**URL:** <YOUR_DEMO_URL> (HTTPS — needed for mic; click through self-signed warning once)
**Admin password:** `admin@nagarai`

> Pre-flight: `curl -sk <YOUR_DEMO_URL>/api/health` → `{"ok":true}`

---

## 0. Quick tour of the Ward Control Room — 1 min
Three views in one page (starfield background):
- **👤 Citizen — File a Complaint** (public): voice/photo/text tabs + GPS/EXIF location
- **🔎 Track Status** (public): complaint ID → progress steps
- **🛡 Admin — Ward Control Room** (login `admin@nagarai`): map, cluster cards, PRT formula

## 1. Intake robustness (multimodal, messy, live) — ~3 min
Run `python scripts/robustness_battery.py --host <YOUR_DEMO_URL>` — it fires the printed
judging scenarios live and prints what the models saw:

| # | Case | Expected |
|---|---|---|
| 1 | **Noisy Tamil voice** (noise injected) | Thanglish verbatim transcript + category/severity |
| 2 | **Sideways photo** | EXIF orientation auto-corrected → correct category |
| 3 | **Mixed-language angry rant** (Hindi+English) | Category + clean one-liner |
| 4 | **Judge-style live text** | Structured complaint, geocoded |
| 5 | **Photo with EXIF GPS** | Exact metadata: make/model/time + **lat/lng from photo EXIF** |

Point out the **"Photo metadata (EXIF)"** line in the receipt stamp, and the **needs-geo
fallback** when nothing pinpoints a location.

## 2. Live 15-complaint dedup run (the 30%) — ~4 min
In the **admin** view → JUDGING SET panel → **Load 15-complaint set** (posts through the server
intake; dedup runs automatically on each submission).

- Watch clusters form **live on the map** and in the cluster cards.
- Open a merged cluster → the LIVE MERGED CLUSTERS panel shows per-member
  `sim % (text · geo · vision)` — the "why merged" audit trail.
- Highlight that **two pothole complaints at different locations did NOT merge** (geo fence).
- Read out the bench metrics: `python scripts/run_bench.py --host <YOUR_API_URL>`
  → **purity 1.0 · coverage 1.0 · merge accuracy 1.0 · category 1.0**.

## 3. Explainable priority (PRT) — ~2 min
- Cluster cards are sorted by priority; the **PRT FORMULA** panel walks the terms live:
  `band(S) · P(affected, log-damp) · T(days) · L(proximity ×1.5)`.
- **Worked example** auto-loads: top issue shows `S=5 · P=0.51 · T=1.00 · L=1.00 · band 1 → 90/100`.
- `python scripts/priority_workthrough.py` shows the live-wire-vs-pothole trap and the band fix.
- A card with **"near <school>"** shows where Overpass found a POI (L=1.5).

## 4. End-to-end loop (the 10%) — ~2 min
1. **File** (voice+photo+text) on a phone → receipt shows category/severity/summary/dedup + EXIF.
2. **Admin** (login) → the new issue appears on the map with its PRT score.
3. Officer clicks **✓ Resolve** → status flips; citizens of the cluster "notified".
4. Citizen opens **Track Status** with their ID → progress bar shows **RESOLVED 🎉**.

## 5. Reports + anti-abuse — 1 min
- **👁 View report** opens the area-segregated markdown report (rendered tables); **⬇ Download**
  saves it, **✉️ Share via email** sends it.
- Show the **category + area filters** and the auto-updating **colour legend** under the map.
- Note: VPN/proxy connections are blocked (themed `/vpn-blocked` page) and admin login has a
  free math human-check.

## 6. Tech-note readout — 30s
Models/endpoints used, canonicalize-then-embed insight (the Tamil-embedding measurement),
severity-band rationale, EXIF-as-location, failure modes (live voice browser-dependent; vision on
ambiguous photos).

---

## Time budget: ~12 min. Buffer: repeat any live filing / let judges poke the dashboard.
