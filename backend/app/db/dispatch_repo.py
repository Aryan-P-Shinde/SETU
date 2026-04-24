"""
DispatchRecord repository — Firestore operations for dispatch_log.
"""

import logging
from typing import Optional

from app.db.firestore_client import COL_DISPATCH_LOG, get_db
from app.models.dispatch import DispatchRecord, DispatchStatus

logger = logging.getLogger(__name__)


async def create(record: DispatchRecord) -> str:
    db = get_db()
    db.collection(COL_DISPATCH_LOG).document(record.id).set(record.to_firestore())
    logger.info(f"Dispatch created: {record.id} volunteer={record.volunteer_id} need={record.needcard_id}")
    return record.id


async def get(dispatch_id: str) -> Optional[DispatchRecord]:
    db = get_db()
    doc = db.collection(COL_DISPATCH_LOG).document(dispatch_id).get()
    if not doc.exists:
        return None
    return DispatchRecord.from_firestore(doc.id, doc.to_dict())


async def update(record: DispatchRecord) -> None:
    db = get_db()
    db.collection(COL_DISPATCH_LOG).document(record.id).set(record.to_firestore())


async def get_active_for_needcard(needcard_id: str) -> Optional[DispatchRecord]:
    db = get_db()
    docs = (
        db.collection(COL_DISPATCH_LOG)
        .where("needcard_id", "==", needcard_id)
        .where("status", "in", [DispatchStatus.pending.value, DispatchStatus.accepted.value, DispatchStatus.en_route.value])
        .limit(1)
        .stream()
    )
    results = [DispatchRecord.from_firestore(d.id, d.to_dict()) for d in docs]
    return results[0] if results else None


async def get_active_for_volunteer(volunteer_id: str) -> Optional[DispatchRecord]:
    db = get_db()
    docs = (
        db.collection(COL_DISPATCH_LOG)
        .where("volunteer_id", "==", volunteer_id)
        .where("status", "in", [DispatchStatus.pending.value, DispatchStatus.accepted.value, DispatchStatus.en_route.value])
        .limit(1)
        .stream()
    )
    results = [DispatchRecord.from_firestore(d.id, d.to_dict()) for d in docs]
    return results[0] if results else None


async def get_history_for_volunteer(volunteer_id: str, limit: int = 20) -> list[DispatchRecord]:
    db = get_db()
    docs = (
        db.collection(COL_DISPATCH_LOG)
        .where("volunteer_id", "==", volunteer_id)
        .order_by("dispatched_at", direction="DESCENDING")
        .limit(limit)
        .stream()
    )
    return [DispatchRecord.from_firestore(d.id, d.to_dict()) for d in docs]
