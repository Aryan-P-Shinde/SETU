# SETU — Disaster Relief Coordination System

> **"Setu" (सेतु) means "bridge" in Sanskrit — a bridge between people in crisis and the volunteers who reach them.**

SETU is an AI-powered volunteer coordination platform that converts unstructured, multi-modal community distress signals — voice messages, photos, handwritten forms, WhatsApp texts — into structured, prioritized, actionable NeedCards, and matches them to the right volunteers with zero friction on either end.

---

## Table of Contents

1. [The Problem](#the-problem)
2. [What SETU Does](#what-setu-does)
3. [Architecture Overview](#architecture-overview)
4. [Core Pipeline — How a Report Becomes a Dispatch](#core-pipeline)
5. [Key Features](#key-features)
6. [Tech Stack](#tech-stack)
7. [Project Structure](#project-structure)
8. [Getting Started](#getting-started)
9. [Environment Variables](#environment-variables)
10. [API Reference](#api-reference)
11. [Testing](#testing)
12. [Deployment](#deployment)
13. [Phase 1 vs. Planned Phases](#phase-1-vs-planned-phases)
14. [Evaluation Prompts & Design Decisions](#evaluation-prompts--design-decisions)

---

## The Problem

Local NGOs and social groups collect enormous amounts of data about community needs — through paper surveys, phone calls, WhatsApp messages, field visits. But this data is:
•	Scattered across multiple places — WhatsApp groups, paper files, spreadsheets, verbal notes
•	Unstructured — messy, inconsistent, not comparable across reports
•	Inaccessible in real-time — no one knows what the biggest problem is right now
•	Hard to act on — even when someone sees a need, connecting a volunteer to it is manual and slow

SETU solves all four of these simultaneously. It is not just a database. It is not just a volunteer app. It is the intelligence layer that sits between raw human observation and coordinated action.


---

## What SETU Does

| Input | What happens | Output |
|---|---|---|
| Field worker types a report | Gemini extracts structured fields, geocodes location, scores urgency | NeedCard in Firestore |
| Same situation reported twice | Hash + semantic dedup detects overlap, merges report counts | Single NeedCard (report_count × 2) |
| Coordinator clicks "Dispatch + Brief" | Volunteer match by haversine distance + skill overlap, Gemini writes a WhatsApp-length brief | DispatchRecord + brief in volunteer's language |
| Time passes | Exponential urgency decay runs hourly | Stale cards auto-archived, urgent ones surface |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        INTAKE CHANNELS                       │
│   Text Form │ Voice (Whisper) │ Image (Gemini OCR) │ WhatsApp│
└──────────────────────┬──────────────────────────────────────┘
                       │  IntakePayload (normalised)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                      INTAKE SERVICE                          │
│  1. Gemini extraction (text → structured fields)             │
│  2. Nominatim geocoding (location_text → lat/lng)            │
│  3. Layer 1 dedup: SHA-256 hash match                        │
│  4. Layer 2 dedup: Gemini embedding + cosine similarity      │
│  5. NeedCard assembly + Firestore write                      │
└──────────────────────┬──────────────────────────────────────┘
                       │  NeedCard (Firestore)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                      DISPATCH ENGINE                         │
│  Haversine distance scoring + skill overlap scoring          │
│  → Best volunteer selected → DispatchRecord created          │
└──────────────────────┬──────────────────────────────────────┘
                       │  DispatchRecord (Firestore)
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                    BRIEF GENERATOR                           │
│  Gemini 1.5 Pro + version-controlled prompt                  │
│  → 60–140 word mission brief in volunteer's language         │
└──────────────────────┬──────────────────────────────────────┘
                       │  Delivery
                       ▼
              FCM push (Phase 1) → WhatsApp/SMS (Phase 2)
```

All intake channels are **thin adapters**. They accept channel-specific input (audio, image bytes, raw text), convert it to a plain text string, wrap it in an `IntakePayload`, and call `process_intake()`. Adding a new channel requires writing one adapter file — zero changes to the core pipeline.

---

## Core Pipeline

### Step 1 — Field Extraction via Gemini

Raw text (however messy, multilingual, or partial) is sent to Gemini with a version-controlled extraction prompt (`prompts/extraction_v1.txt`). The model returns a validated JSON object containing:

- `need_type` — classified into: `medical`, `food`, `shelter`, `water`, `rescue`, `logistics`, `other`
- `description_clean` — normalised description preserving all factual details
- `urgency_score` — float 0.0–10.0, with explicit chain-of-thought reasoning stored for NGO audit
- `affected_count` — number of people affected
- `skills_needed` — from a fixed canonical skill list (e.g. `search_rescue`, `medical_paramedic`)
- `location_text` — raw location as mentioned, not geocoded yet

On parse failure, the service retries once. On two consecutive failures, the raw input is stored with `extraction_failed=True` and flagged for human review.

### Step 2 — Geocoding via Nominatim

`location_text` is sent to Nominatim (OpenStreetMap) for lat/lng resolution. The service returns a confidence score:

- `0.9` — street/landmark level match
- `0.7` — neighbourhood/area level
- `0.4` — city/district level
- `0.0` — failed

No API key is required. Nominatim has strong coverage of Indian cities, districts, and landmarks.

### Step 3 — Deduplication (Two Layers)

**Layer 1 — Exact hash:** A SHA-256 hash of the normalised description is checked against all existing open NeedCards of the same type. Exact match → merge.

**Layer 2 — Semantic dedup:** If geo confidence ≥ 0.3 and no exact match, the description is embedded using Gemini `text-embedding-004`. Nearby open cards of the same type are fetched from Firestore, their stored embeddings are retrieved, and cosine similarity is computed. If similarity ≥ 0.88 → merge.

On merge, the existing card's `report_count` increments and its urgency is escalated if the new report scores higher. The signal gets stronger, not noisier.

### Step 4 — NeedCard Assembly

A `NeedCard` Pydantic model is assembled with all extracted, geocoded, and computed fields and written to Firestore collection `need_cards`. An embedding is stored asynchronously (non-blocking) for future dedup lookups.

### Step 5 — Dispatch Matching

`POST /dispatch/quick` accepts a `needcard_id`. The engine:
1. Fetches all available volunteers from Firestore
2. For each volunteer, computes: haversine distance to the NeedCard location + skill overlap count
3. Selects the volunteer with the best combined score
4. Creates a `DispatchRecord` in Firestore with status `pending`

### Step 6 — Brief Generation

`POST /brief/{dispatch_id}` pulls the NeedCard context, the matched volunteer's skills and language preference, and calls Gemini 1.5 Pro with a version-controlled brief prompt (`prompts/brief_v1.txt`). The result is a 60–140 word, WhatsApp-sendable mission brief written in the volunteer's language (English, Hindi, Bengali, Marathi, Telugu, Tamil, or Odia).

The brief is stored in `DispatchRecord.brief_text` in draft state until the NGO coordinator approves and triggers delivery.

### Step 7 — Urgency Decay

Urgency scores decay over time using exponential decay: `U(t) = U₀ · e^(−0.05t)`, giving a half-life of ~14 hours for a base-10 card. In production this runs hourly via Cloud Scheduler. During demos, `POST /admin/run-decay` triggers it manually. Cards that decay below threshold are auto-marked `stale`.

---

## Key Features

### Multi-Channel Intake

Every intake channel normalises its input to a plain text string before calling the core pipeline. This is not a design aspiration — it is enforced by the `IntakePayload` contract in `intake_service.py`.

| Channel | Input | Conversion |
|---|---|---|
| Text | Typed report | Passthrough |
| Voice | Audio file | OpenAI Whisper (local or API) |
| Image | Photo of handwritten form / signboard | Gemini Vision OCR |
| WhatsApp | Webhook payload | Adapter stub (Phase 2) |

### Two-Layer Semantic Deduplication

Most disaster coordination systems have no dedup at all. SETU's two-layer approach handles both exact reposts and paraphrased duplicates across different reporters. The 0.88 cosine similarity threshold was calibrated against the extraction eval set in `tests/eval/`.

### Urgency Scoring with Audit Trail

Every urgency score comes with `urgency_reasoning` — the model's step-by-step chain of thought preserved verbatim in Firestore. This allows NGO staff to audit, challenge, or override any score and is a requirement for responsible deployment in humanitarian contexts.

### Language-Aware Brief Generation

Volunteer mission briefs are generated in the volunteer's registered language preference. The brief prompt enforces strict factual grounding — the model is explicitly instructed not to invent details, mark any uncertainty with `[?]`, and omit fields that are null rather than writing placeholders.

### Live / Seed Data Toggle

The frontend dashboard shows a `LIVE` (green) or `SEED` (amber) badge. When the backend is reachable, the dashboard reads from Firestore in real time — submit a report and the NeedCard appears within seconds. When the backend is unreachable, it falls back to seed data so the UI remains demonstrable.

---

## Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| Backend framework | FastAPI (Python 3.11+) | Async-native, auto-generates OpenAPI docs |
| Database | Google Cloud Firestore | Real-time listeners, no schema migrations |
| AI — extraction & brief | Gemini 1.5 Pro | Google DPA compliance; strong multilingual |
| AI — embeddings | Gemini `text-embedding-004` | 768-dim; fast cosine similarity |
| AI — voice transcription | OpenAI Whisper (local) | Free, offline-capable, good Hindi/Bengali |
| Geocoding | Nominatim (OpenStreetMap) | Free, no key, strong Indian coverage |
| Frontend | React 18 + TypeScript + Vite | Fast iteration; strict types |
| Auth | Firebase Auth | Integrates with Firestore security rules |
| Container | Docker → Cloud Run | Scale-to-zero cost model |
| CI | GitHub Actions | Lint + test on every PR |

---

## Project Structure

```
setu/
├── backend/
│   ├── app/
│   │   ├── core/
│   │   │   └── config.py           # Pydantic settings (env vars)
│   │   ├── db/
│   │   │   ├── firestore_client.py # Singleton Firestore client
│   │   │   ├── needcard_repo.py    # NeedCard CRUD + geo queries
│   │   │   ├── volunteer_repo.py   # Volunteer CRUD
│   │   │   └── dispatch_repo.py    # DispatchRecord CRUD
│   │   ├── models/
│   │   │   ├── needcard.py         # NeedCard Pydantic model (schema v1.0)
│   │   │   ├── volunteer.py        # Volunteer model
│   │   │   └── dispatch.py         # DispatchRecord model
│   │   ├── prompts/
│   │   │   ├── extraction_v1.txt   # Gemini extraction prompt (version-controlled)
│   │   │   └── brief_v1.txt        # Gemini brief prompt (version-controlled)
│   │   ├── routers/
│   │   │   ├── health.py           # GET /health
│   │   │   ├── needcards.py        # NeedCard read endpoints
│   │   │   ├── dispatch.py         # Dispatch + decay endpoints
│   │   │   ├── brief.py            # Brief generation + delivery
│   │   │   └── channels/
│   │   │       ├── text_channel.py     # POST /intake/text
│   │   │       ├── voice_channel.py    # POST /intake/voice
│   │   │       ├── image_channel.py    # POST /intake/image
│   │   │       └── whatsapp_channel.py # POST /intake/whatsapp (Phase 2 stub)
│   │   └── services/
│   │       ├── intake_service.py       # Core pipeline (channel-agnostic)
│   │       ├── extraction_service.py   # Gemini field extraction
│   │       ├── brief_service.py        # Gemini brief generation
│   │       ├── delivery_service.py     # FCM / WhatsApp delivery
│   │       ├── geo_service.py          # Nominatim geocoding
│   │       ├── gemini_ocr_service.py   # Gemini Vision OCR
│   │       └── whisper_service.py      # Whisper transcription
│   ├── tests/
│   │   ├── eval/                       # LLM eval sets (extraction + brief)
│   │   ├── integration/                # Live Whisper tests
│   │   └── test_*.py                   # Unit + integration tests
│   ├── scripts/
│   │   └── seed.py                     # Firestore seeding script
│   ├── Dockerfile
│   └── pyproject.toml
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── DashboardPage.tsx    # NGO coordinator dashboard
│       │   ├── VolunteerApp.tsx     # Volunteer-facing mobile UI
│       │   ├── LandingPage.tsx      # Public landing page
│       │   └── LoginPage.tsx        # Firebase auth
│       ├── components/
│       │   └── NeedCardComponent.tsx
│       └── lib/
│           ├── api.ts               # Typed Axios API client
│           ├── firebase.ts          # Firebase SDK init
│           └── seedData.ts          # Fallback seed data
├── infra/
│   ├── cloudrun/service.yaml        # Cloud Run service definition
│   └── firebase/firestore.indexes.json
├── firestore.rules                  # Firestore security rules
├── Makefile                         # Dev, test, deploy commands
└── DEMO_NARRATIVE.md               # Presenter guide + judge Q&A prep
```

---

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+
- A Google Cloud project with Firestore enabled
- A Gemini API key (Google AI Studio)
- `ffmpeg` installed (required for local Whisper)

### Backend

```bash
# 1. Clone and enter the repo
git clone https://github.com/your-org/setu.git && cd setu

# 2. Install backend dependencies
make install
# equivalent to: pip install -e ".[dev]" in backend/

# 3. Configure environment variables
cp backend/.env.example backend/.env
# Fill in GEMINI_API_KEY, FIREBASE_PROJECT_ID, GOOGLE_APPLICATION_CREDENTIALS

# 4. Start the development server
make dev
# Server runs at http://localhost:8000
# API docs at http://localhost:8000/docs (only when DEBUG=true)
```

### Frontend

```bash
# 5. Install frontend dependencies
make frontend-install

# 6. Configure frontend env
cp frontend/.env.example frontend/.env
# Set VITE_API_BASE_URL=http://localhost:8000/api/v1
# Set VITE_FIREBASE_* values from your Firebase project settings

# 7. Start the dev server
make frontend-dev
# Runs at http://localhost:5173
```

### Seed Firestore (optional)

```bash
# Populate Firestore with realistic sample NeedCards and volunteers
cd backend && python scripts/seed.py
```

---

## Environment Variables

### Backend (`backend/.env`)

| Variable | Required | Description |
|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | Yes | Path to GCP service account JSON |
| `FIREBASE_PROJECT_ID` | Yes | Your Firebase project ID |
| `GEMINI_API_KEY` | Yes | Google AI Studio API key |
| `GCS_BUCKET_NAME` | Yes | Cloud Storage bucket for uploaded images |
| `OPENAI_API_KEY` | No | Required only if `WHISPER_MODE=api` |
| `WHISPER_MODE` | No | `local` (default) or `api` |
| `WHISPER_MODEL` | No | `base` (default), `small`, `medium` |
| `SECRET_KEY` | Yes | JWT signing key — change in production |
| `DEBUG` | No | `true` enables `/docs` endpoint |
| `GROQ_API_KEY` | No | Demo fallback LLM — not for production |

### Frontend (`frontend/.env`)

| Variable | Required | Description |
|---|---|---|
| `VITE_API_BASE_URL` | Yes | Backend URL (e.g. `https://setu-api-xxx.run.app/api/v1`) |
| `VITE_FIREBASE_API_KEY` | Yes | Firebase project API key |
| `VITE_FIREBASE_AUTH_DOMAIN` | Yes | Firebase auth domain |
| `VITE_FIREBASE_PROJECT_ID` | Yes | Firebase project ID |
| `VITE_FIREBASE_STORAGE_BUCKET` | Yes | Firebase storage bucket |
| `VITE_FIREBASE_MESSAGING_SENDER_ID` | Yes | FCM sender ID |
| `VITE_FIREBASE_APP_ID` | Yes | Firebase app ID |

---

## API Reference

All routes are prefixed `/api/v1`. Full interactive docs available at `/docs` when `DEBUG=true`.

### Intake

| Method | Route | Description |
|---|---|---|
| `POST` | `/intake/text` | Submit a text report |
| `POST` | `/intake/voice` | Submit an audio file (WAV/MP3) — transcribed via Whisper |
| `POST` | `/intake/image` | Submit an image of a handwritten form — OCR via Gemini Vision |
| `POST` | `/intake/whatsapp` | WhatsApp webhook *(Phase 2 — stub returns 501)* |

All intake endpoints return `IntakeResult`:
```json
{
  "needcard_id": "uuid",
  "is_duplicate": false,
  "merged_into": null,
  "extraction_failed": false,
  "needs_review": false,
  "urgency_score": 8.5,
  "need_type": "rescue"
}
```

### NeedCards

| Method | Route | Description |
|---|---|---|
| `GET` | `/needcards` | List open NeedCards, sorted by urgency |
| `GET` | `/needcards/{id}` | Get a single NeedCard |

### Dispatch

| Method | Route | Description |
|---|---|---|
| `POST` | `/dispatch/quick` | Create a dispatch — auto-selects best volunteer if `volunteer_id` omitted |
| `GET` | `/dispatch/{dispatch_id}` | Get a dispatch record |
| `POST` | `/dispatch/{dispatch_id}/accept` | Volunteer accepts the mission |
| `POST` | `/dispatch/{dispatch_id}/en_route` | Volunteer marks themselves en route |
| `POST` | `/dispatch/{dispatch_id}/complete` | Mission completed |
| `POST` | `/dispatch/{dispatch_id}/cancel` | Cancel with reason |
| `POST` | `/admin/run-decay` | Trigger urgency decay manually (replaces Cloud Scheduler during demos) |

### Brief

| Method | Route | Description |
|---|---|---|
| `POST` | `/brief/{dispatch_id}` | Generate a Gemini brief for a dispatch |
| `POST` | `/brief/{dispatch_id}/send` | Deliver the brief via FCM *(Phase 2: also WhatsApp)* |

---

## Testing

```bash
# Run all backend tests
make test

# Run lint checks
make lint

# Auto-fix lint issues
make lint-fix
```

### Test Coverage

| Test file | What it covers |
|---|---|
| `test_extraction.py` | Gemini extraction — field accuracy, failure modes, retry logic |
| `test_brief.py` | Brief generation — word count, language switching, null field handling |
| `test_channels.py` | All four intake channel adapters |
| `test_image_intake.py` | Gemini OCR pipeline |
| `test_voice_intake.py` | Whisper transcription pipeline |
| `test_models.py` | Pydantic model validation |
| `tests/eval/` | LLM eval sets — extraction accuracy across 20 synthetic reports, brief quality scoring |
| `tests/integration/` | Live Whisper transcription (requires audio file) |

### LLM Evaluation

`tests/eval/` contains structured eval sets for both the extraction and brief generation prompts. These are used to measure prompt quality before committing prompt changes. Run them with:

```bash
cd backend && python tests/eval/run_extraction_eval.py
cd backend && python tests/eval/run_brief_eval.py
```

---

## Deployment

### Backend — Cloud Run

```bash
# Build and deploy to Cloud Run (asia-south1 region)
make deploy-backend

# Equivalent to:
gcloud run deploy setu-api \
  --source backend/ \
  --region asia-south1 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=$GEMINI_API_KEY,FIREBASE_PROJECT_ID=$FIREBASE_PROJECT_ID
```

The Cloud Run service definition is in `infra/cloudrun/service.yaml`. Secrets are managed via Google Secret Manager and referenced in the service YAML. The service scales to zero when idle (cost-efficient for a prototype) and up to 10 instances under load.

**Memory note:** With `WHISPER_MODE=local` and `whisper_model=base`, the container needs ~512 MB RAM. For `medium` or `large` Whisper models, increase to 4 GB in `service.yaml`.

### Frontend — Firebase Hosting

```bash
make deploy-frontend
# equivalent to: firebase deploy --only hosting
```

### CI/CD

GitHub Actions runs on every PR to `main` or `dev`:
- Backend: `ruff` lint + `pytest` test suite
- Frontend: ESLint + Vite production build

---

## Phase 1 vs. Planned Phases

SETU is a living system. Phase 1 is the intake-to-dispatch pipeline. The architecture is designed so each subsequent phase is additive — no existing code changes.

### Phase 1 — Complete ✅

- Text intake → Gemini extraction → NeedCard → Firestore
- Geocoding via Nominatim
- Two-layer deduplication (hash + semantic)
- Volunteer matching by distance + skill
- Gemini brief generation (all 7 Indian languages)
- Exponential urgency decay with manual trigger
- NGO coordinator dashboard (live Firestore reads)
- Volunteer app UI prototype
- FCM delivery stub (schema and service built, token registration pending)
- CI pipeline (lint + test)

### Phase 2 — Planned: WhatsApp Delivery & FCM Push 📋

The `delivery_service.py` is already architected as a strategy dispatcher. Adding WhatsApp delivery means:
1. Implement `_send_whatsapp()` using Twilio or Meta Cloud API
2. Add one `elif channel == DeliveryChannel.whatsapp` branch
3. Activate the `/intake/whatsapp` stub by wiring it to the real Twilio webhook parser

The volunteer app already has the FCM token storage schema in Firestore. Full push delivery requires registering the token on the volunteer's first app launch and passing it to `deliver_brief()`.

### Phase 3 — Planned: Field Worker PWA 📋

A progressive web app for field workers to submit reports from low-connectivity environments. Reports queue locally and sync when connectivity returns. The intake API already accepts all three input types — the PWA is a new channel adapter, not a new backend feature.

### Phase 4 — Planned: Analytics Dashboard for NGOs 📋

An aggregate view showing: reports by region, need type distribution, volunteer utilisation rates, average time-to-dispatch, and urgency decay curves. Data is already stored in Firestore with sufficient structure for these queries.

### Phase 5 — Planned: Multi-Tenancy 📋

Support multiple NGOs operating independently in the same region, with isolated Firestore namespaces, separate volunteer pools, and shared-need detection for cross-NGO coordination.

---

## Evaluation Prompts & Design Decisions

This section documents the reasoning behind key technical decisions for judges reviewing the architecture.

### Why Gemini for extraction — not a rule-based parser?

Disaster field reports are inherently unstructured. They come in mixed languages, include local place names, use colloquial urgency language, and omit fields inconsistently. A rule-based parser would require thousands of patterns and still fail on novel inputs. Gemini handles this reliably with a single, version-controlled prompt that can be improved without code changes.

### Why two-layer dedup instead of one?

Layer 1 (hash) is O(1) and catches the common case: the same person submitting twice, or a coordinator forwarding a report they already logged. Layer 2 (semantic embedding) catches the real problem: two different people reporting the same trapped family from different angles, in different words. Without Layer 2, the same situation generates multiple dispatches and multiple volunteers arrive at the same location, wasting scarce resources.

### Why Nominatim instead of Google Maps Geocoding API?

Cost and data sovereignty. Nominatim is free, runs on OpenStreetMap data, and has strong coverage of Indian sub-district level geography. For a system deployed by resource-constrained NGOs, zero geocoding cost is a meaningful design constraint. The confidence scoring (0.0–0.9) communicates to downstream systems exactly how much to trust the coordinates.

### Why version-controlled prompts in `.txt` files?

Prompts are the core logic of an LLM-powered system. Storing them in code constants makes them invisible to code review, impossible to diff meaningfully, and hard to test in isolation. Version-controlled prompt files make prompt changes first-class commits — reviewable, rollback-able, and testable against the eval sets.

### Why exponential decay for urgency?

An open help request that hasn't been fulfilled after 14 hours may have been resolved through other means, or the situation may have evolved. Exponential decay with λ=0.05 gives a half-life of ~14 hours — a rescue card scored 10 at intake scores 5 after 14 hours and is auto-staled after ~3 days. This prevents old, unresolved cards from permanently clogging the priority feed.

### Why does the brief have a word count constraint?

Volunteers in the field read briefs on mobile phones, often on slow connections, under stress. A brief that exceeds WhatsApp's comfortable reading length at a glance will not be read carefully. The 60–140 word constraint is enforced in the prompt and validated in `brief_service.py`. The prompt was calibrated against real volunteer feedback from AIDMI field reports.

---

## Acknowledgements

- AIDMI (All India Disaster Mitigation Institute) for published field data that grounded the problem statement
- OpenStreetMap and the Nominatim project for free geocoding
- The FastAPI, Pydantic, and Firebase teams for the foundational libraries

---

*Built for the Google Solution Challenge · Phase 1 submission · April 2026*
