.PHONY: dev test lint deploy install

PYTHON := python3
PIP := pip3
UVICORN_HOST := 0.0.0.0
UVICORN_PORT := 8000

install:
	cd backend && $(PIP) install -e ".[dev]" --break-system-packages

dev:
	cd backend && uvicorn app.main:app --reload --host $(UVICORN_HOST) --port $(UVICORN_PORT)

test:
	cd backend && pytest -v --tb=short

lint:
	cd backend && ruff check . && ruff format --check .

lint-fix:
	cd backend && ruff check --fix . && ruff format .

# ── Frontend ────────────────────────────────────────────────────
frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build

# ── Deploy (Cloud Run) ──────────────────────────────────────────
deploy-backend:
	gcloud run deploy solution-challenge-api \
		--source backend/ \
		--region asia-south1 \
		--allow-unauthenticated \
		--set-env-vars GEMINI_API_KEY=$$GEMINI_API_KEY,FIREBASE_PROJECT_ID=$$FIREBASE_PROJECT_ID

deploy-frontend:
	firebase deploy --only hosting

deploy: deploy-backend deploy-frontend