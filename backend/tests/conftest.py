"""
pytest configuration — shared fixtures and environment setup.

Sets env vars before any import so services that read os.getenv() at
module level (e.g. extraction_service checking GEMINI_API_KEY) get
safe test values rather than raising RuntimeError on import.
"""

import os
import pytest

# ── Set safe defaults before any app code is imported ─────────────────────────
# These are overridden per-test via monkeypatch or patch() where needed.
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key-not-real")
os.environ.setdefault("FIREBASE_PROJECT_ID", "test-project")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-real")
os.environ.setdefault("GCS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("WHISPER_MODE", "local")
os.environ.setdefault("WHISPER_MODEL", "base")


# ── Prevent Firestore from initializing during tests ──────────────────────────
# Tests that need DB operations mock needcard_repo/volunteer_repo directly.
# This fixture patches get_db() so tests that accidentally call it fail
# clearly rather than hanging on a real network connection.
@pytest.fixture(autouse=True)
def no_real_firestore(monkeypatch):
    """
    Block real Firestore connections in unit tests.
    Integration tests that need real Firestore should be in tests/integration/
    and can override this fixture.
    """
    def _blocked_get_db():
        raise RuntimeError(
            "Unit test attempted a real Firestore connection. "
            "Mock needcard_repo / volunteer_repo / dispatch_repo instead."
        )

    monkeypatch.setattr("app.db.firestore_client.get_db", _blocked_get_db)