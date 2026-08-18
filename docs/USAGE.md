# NagarAI — Usage Guide

NagarAI is a **civic complaint intelligence engine**: citizens file complaints naturally
(voice note, photo, or text — in Tamil, Hindi, English, or any mix), and officials get a
**deduplicated, categorised, prioritised, mapped** queue with explainable ranking.

**Live demo:** `<YOUR_DEMO_URL>` (trusted HTTPS — geolocation + mic work)
**Admin password:** `<ADMIN_PASSWORD>`

---

## Quick tour (3 views)

The app has three views, switched from the bar at the top:

| View | Who | What it does |
|---|---|---|
| `[Citizen — File a complaint]` | Public | File a complaint by voice / photo / text |
| `[Track — status]` | Public | Check a filed complaint by its ID |
| `[Admin — Ward control room]` | Officials (password) | Map, cluster cards, PRT ranking, judging set |

---

## 1. Citizen — File a complaint

### Step-by-step
1. Open the **Citizen** view.
2. Choose an input tab: **Text rant**, **Voice note**, or **Photo**.
3. **Text** — type or paste it however you'd say it:
   > `anna nagar 2nd avenue la periya pothole, romba deep, school kitta`
4. **Voice** — tap **🎙️ Start recording**, pick your language from the dropdown
   (English default, plus Tamil, Hindi, Kannada, Telugu, Malayalam, Bengali, Marathi, Gujarati,
   Punjabi). Text streams **live** into the box as you speak (native script, e.g. Tamil → தமிழ்),
   then tap stop.
5. **Photo** — tap the upload box, pick/take a photo. **No text description needed** — the AI
   classifies the issue (pothole/garbage/streetlight/waterlogging or a NEW AI-created category)
   from the photo alone, and auto-locates it from EXIF GPS or visible street signage. You can
   optionally add a note in words.
6. **Location** — auto-fills from your browser GPS (no tap needed). Or type the area name
   in the text; or tap the 📍 button.
7. Tap **Submit & run AI intake**.

### The receipt
After submitting you get a receipt showing:
- **Ticket ID** (your tracking number)
- **Category** + severity (1–5)
- **Location resolved** (from GPS, photo EXIF, or text)
- **Clean summary** (one clear English line)
- **Photo metadata** (EXIF) when a photo was used
- **Dedup result** — whether it merged into an existing issue

> **Note the ticket ID** — you'll use it in the Track view.

---

## 2. Track — status

1. Open the **Track** view.
2. Enter your **complaint ID** (from the receipt) and press **Go**.
3. You'll see: category, severity, department, issue group, affected-citizen count,
   and a **progress bar**: `Open → Assigned → In Progress → Resolved`.

---

## 3. Admin — Ward control room

Log in with the password (`<ADMIN_PASSWORD>`).

### Ward map
- Cluster markers sized by affected count, coloured by category.
- Click a marker for its popup (category, priority, affected, summary).
- **Fullscreen** button expands the map; filters hide in fullscreen and return on exit.

### Filters
- **Category** (pothole / garbage / streetlight / waterlogging / AI-created types)
- **Status** (open / assigned / in progress / resolved)
- **Sort** (priority ↓ / days pending ↓ / affected ↓)

### Cluster cards
Each card shows:
- Category + department + ticket ref (`CR-0001`)
- **PRT stamp** + band
- Summary, affected count, days pending, proximity badge, SLA timer
- Status **actions**: `Assign` → `In progress` → `Resolve` (open cards)

### PRT (priority) formula (transparent)
```
score = band(Severity) · P(affected, log-damped) · T(days, saturating) · L(proximity ×1.5)
```
- **Band 1** (S≥5 / hazard): always 90–99, above everything.
- Within bands, rank = P × T × L.
- Every term is shown on the cards and in the **PRT formula** panel.

### Judging set (live dedup demo)
- **Load 15-complaint set** posts 15 real complaints through the AI pipeline (3-parallel).
- **Run live dedup** re-renders the clusters.
- The **LIVE MERGED CLUSTERS** panel shows each merge with its similarity scores
  (text · geo · vision) — the "why merged" audit trail.

---

## 4. New categories (AI-created)

When a complaint doesn't fit the four standard types, the AI **creates a new category**:
- Example: "stray dogs attacking people near the bus depot" → category `stray_dogs`,
  label **"Stray Dog Menace"**, with an **AI-picked colour** (`#FF5A1F`).
- The new category appears in the map, cards, and filters automatically.

---

## 5. Voice transcription (how it works)

| Language chosen | What happens |
|---|---|
| English (default) | Live transcript in English as you speak |
| Tamil / Hindi / Kannada / Telugu / Malayalam / Bengali / Marathi / Gujarati / Punjabi | Live transcript in the language's native script |

Transcription runs **in your browser** via the Web Speech API — words appear live as you speak
(interim results), and stop when you tap stop. No server round-trip, no waiting.

---

## 6. Location sources (in priority order)

1. **Browser GPS** — auto-filled when you allow location (recommended).
2. **Photo EXIF GPS** — exact coordinates embedded in the photo.
3. **Visible signage** — the vision model reads street signs/landmarks from the photo.
4. **Text mention** — area names in your complaint are geocoded.
5. **Needs pin** — if none found, the issue appears without a pin and can be located later.

---

## 7. Tips for a smooth demo

- **Use HTTPS** (`<YOUR_DEMO_URL>`) so mic + location work.
- **Allow location** on your phone when the browser asks.
- **Speak clearly** for voice; background noise is handled but a quiet clip is best.
- **Keep the ticket ID** when you file — it's your tracking key.
- Admin card actions: assign first, then progress, then resolve.
