"""
Firestore client — singleton, lazy-initialized.

All DB access goes through get_db(). This keeps the client a single instance
across the process lifetime and makes it easy to mock in tests.

Collections:
  need_cards    — NeedCard documents
  volunteers    — Volunteer documents
  dispatch_log  — DispatchRecord documents

Indexes (defined in firestore.indexes.json, deployed via `firebase deploy --only firestore`):
  need_cards:   status + urgency_score_eff DESC
  volunteers:   availability + geohash_5
  need_cards:   VECTOR index on embedding field (Firestore native vector search)
"""

import logging
import os
from typing import Optional

logger = logging.getLogger(__name__)

# Collection name constants — single source, no string literals elsewhere
COL_NEED_CARDS   = "need_cards"
COL_VOLUNTEERS   = "volunteers"
COL_DISPATCH_LOG = "dispatch_log"

_db = None


def get_db():
    """
    Return the Firestore client, initializing it once.
    Safe to call multiple times — returns the same instance.
    """
    global _db
    if _db is not None:
        return _db

    from app.core.config import settings
    project_id = settings.FIREBASE_PROJECT_ID
    creds_path = settings.GOOGLE_APPLICATION_CREDENTIALS

    if not project_id:
        raise RuntimeError("FIREBASE_PROJECT_ID not set in environment")

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore

        if not firebase_admin._apps:
            if creds_path and os.path.exists(creds_path):
                cred = credentials.Certificate(creds_path)
                firebase_admin.initialize_app(cred, {"projectId": project_id})
            else:
                # Cloud Run: uses Application Default Credentials automatically
                firebase_admin.initialize_app(options={"projectId": project_id})

        _db = firestore.client()
        logger.info(f"Firestore initialized for project: {project_id}")
        return _db

    except Exception as e:
        logger.error(f"Firestore init failed: {e}")
        raise


def reset_db_for_testing():
    """Call in test teardown to force re-initialization with mocked client."""
    global _db
    _db = None