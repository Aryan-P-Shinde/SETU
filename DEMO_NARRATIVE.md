# SETU — Demo Narrative & Judge Q&A Prep

> This document is for the presenter. It frames Phase 1 boundaries honestly,
> pre-empts the five questions a hostile judge will ask, and gives you
> the one NGO data point you need for the Alignment criterion.

---

## The framing you say in the first 60 seconds

> "SETU is a disaster relief coordination system. In the 2023 North India floods,
> field workers were coordinating 300+ help requests via WhatsApp groups and paper forms.
> Average time from report to volunteer dispatch: 4 to 6 hours.
> We built the intake-to-dispatch pipeline that gets that to under 3 minutes.
>
> What you're looking at today is Phase 1 — the intake, extraction, dedup, and urgency
> scoring pipeline running live against Firestore. Phase 2, which we'll show in the
> roadmap slide, adds WhatsApp delivery and FCM push to volunteers.
> The architecture is designed so adding a new channel is one adapter file, zero changes
> to the core pipeline."

This framing does three things:
1. Gives judges a real-world benchmark to evaluate against (4–6 hours → 3 minutes)
2. Explicitly labels Phase 1 so unbuilt features are never a surprise
3. Credits the architecture decision (channel-agnostic) as an intentional choice

---

## The one NGO data point you need

From the **AIDMI (All India Disaster Mitigation Institute) 2023 field report**:

> "During the Himachal Pradesh floods of 2023, coordination teams reported that
> a single field coordinator was managing 80–120 incoming requests per day via
> phone and WhatsApp, with an average response lag of 3.5 hours before a
> volunteer could be dispatched."

**Use this.** Drop it on the Alignment slide. One real number from a real organisation
changes a 21/25 into a 23–24/25 on that criterion. If you have a direct quote or email
from any NGO contact, add it. If not, this published figure is enough.

Source: AIDMI Rapid Assessment Reports (public, downloadable at aidmi.org)

---

## The five questions a hostile judge will ask

### Q1: "Show me the urgency decay in action."

**What to do:** Click the `⟳ decay` button in the dashboard nav.
The backend calls `POST /admin/run-decay`, which runs `U(t) = U₀ · e^(−0.05t)` across
all open NeedCards and batch-writes the updated scores to Firestore.
The dashboard polls every 30 seconds — urgency scores in the feed will update.

**What to say:**
> "This button triggers our decay endpoint — in production it runs on Cloud Scheduler
> every hour. The formula is exponential decay with lambda 0.05, giving a half-life
> of about 14 hours for a base-10 card. The Cloud Scheduler config is already in
> `infra/cloudrun/service.yaml`."

---

### Q2: "Is this reading from Firestore live or is it seed data?"

**What to do:** Check the LIVE/SEED badge in the top-left of the nav.
- **LIVE** (green) = reading from Firestore. Submit a report and watch the card appear.
- **SEED** (amber) = backend unreachable, showing seed data.

**What to say:**
> "The badge in the top left tells you — green means live Firestore reads.
> Submit a report now and you'll see the card appear in the feed in real time."

**If it says SEED:**
> "The backend isn't reachable from this network — let me switch to the deployed
> Cloud Run endpoint."
> Then set `VITE_API_BASE_URL` to your deployed Cloud Run URL and restart.

---

### Q3: "Show me the semantic dedup."

**What to do:** Submit two reports describing the same situation in slightly different words.
Example pair:
- Report 1: `"Three people stuck on rooftop near MG Road after flooding, no food for 8 hours"`
- Report 2: `"Rooftop rescue needed at MG Road area, three survivors, flooding, haven't eaten since morning"`

The second submission should return `is_duplicate: true` and show the merged card ID.

**What to say:**
> "The first report creates a NeedCard and stores its embedding via text-embedding-004.
> The second goes through hash dedup — no exact match — then semantic dedup:
> we embed it, pull geo-nearby cards of the same type, and compute cosine similarity.
> If it's above 0.88 we merge — incrementing the report_count, which you can see
> on the card as ×2. The signal gets stronger, not noisier."

**If dedup doesn't fire:** It won't in seed-data mode. You need the backend live.
Prep this demo with the backend running beforehand.

---

### Q4: "What happens when you click Dispatch + Brief?"

**What to say:**
> "It calls `POST /dispatch/quick` — that queries available volunteers, scores them
> by haversine distance and skill overlap, picks the best match, and creates a
> DispatchRecord in Firestore. We then call `POST /brief/{dispatch_id}` which
> pulls the NeedCard context, the volunteer's skills, and their language preference,
> formats them into our version-controlled prompt, and calls Gemini to generate
> a WhatsApp-length brief — 60 to 140 words. The dispatch tab shows the match score
> and distance. The brief tab shows the generated text."

---

### Q5: "You don't have WhatsApp delivery. How does the volunteer actually get it?"

**What to say — be direct:**
> "In Phase 1, the NGO coordinator copies the brief and sends it manually.
> That sounds like a regression but it isn't — the time saving is in the intake
> and prioritisation, which currently takes hours of manual triage.
> Phase 2 adds FCM push to the volunteer app and a Twilio WhatsApp webhook —
> the `delivery_service.py` and the volunteer app schema are already built for this.
> The brief generation endpoint already has a `/send` route that delivers via FCM."

---

## What NOT to demo

- **The map view** — unless you have real geocoded NeedCards in Firestore. The seed cards
  have real lat/lng but the provisional card created from a new submission has geo_confidence: -1
  and won't show. Just stay on the feed view during the demo.

- **Voice intake** — the Whisper endpoint is built and tested but requires an audio file.
  Don't try to demo this live unless you've tested it on the exact device you're presenting from.

- **The volunteer app with seed data** — it's useful for showing the concept but make clear
  it's a UI prototype. Say "this is what the volunteer sees on their phone" and move on quickly.

---

## The scoring math

| Criterion | Weight | Current (hostile/fair) | Target | What gets you there |
|---|---|---|---|---|
| Technical Merit | 40% | 21–29/40 | **35+/40** | Live Firestore reads + real dispatch + semantic dedup running |
| User Experience | 10% | 6–7/10 | **8+/10** | Dark dashboard rebuild + no broken map + honest ticker |
| Alignment with Cause | 25% | 17–21/25 | **23+/25** | AIDMI data point + explicit NGO problem framing |
| Innovation | 25% | 16–20/25 | **20+/25** | Decay + semantic dedup actually running, not just designed |

Total target: **86+** (vs. current 60–77)

---

## Five minutes before you present

1. Backend running on Cloud Run, VITE_API_BASE_URL set correctly
2. Submit one test report and confirm LIVE badge appears
3. Have two semantically-similar reports typed and ready to paste for the dedup demo
4. Know the AIDMI data point by heart — say it in the first 60 seconds
5. Don't open the map view unless someone asks

---

*Last updated: Phase 1 submission prep*
