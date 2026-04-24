"""
Volunteer repository — Firestore operations for Volunteers.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.db.firestore_client import COL_VOLUNTEERS, get_db
from app.models.volunteer import AvailabilityStatus, Volunteer

logger = logging.getLogger(__name__)


async def create(volunteer: Volunteer) -> str:
    db = get_db()
    db.collection(COL_VOLUNTEERS).document(volunteer.id).set(volunteer.to_firestore())
    return volunteer.id


async def get(volunteer_id: str) -> Optional[Volunteer]:
    db = get_db()
    doc = db.collection(COL_VOLUNTEERS).document(volunteer_id).get()
    if not doc.exists:
        return None
    return Volunteer.from_firestore(doc.id, doc.to_dict())


async def update(volunteer: Volunteer) -> None:
    volunteer.touch()
    db = get_db()
    db.collection(COL_VOLUNTEERS).document(volunteer.id).set(volunteer.to_firestore())


async def update_fields(volunteer_id: str, fields: dict) -> None:
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    db = get_db()
    db.collection(COL_VOLUNTEERS).document(volunteer_id).update(fields)


async def find_available_in_geohashes(geohash_neighbors: list[str]) -> list[Volunteer]:
    """
    Query available volunteers whose geohash_5 is in the neighbor set.
    Requires composite index: availability + geohash_5.
    Result is post-filtered by exact haversine distance in match engine.
    """
    db = get_db()
    # Firestore 'in' operator supports max 30 values; geohash_5 neighbor set is 9
    docs = (
        db.collection(COL_VOLUNTEERS)
        .where("availability", "==", AvailabilityStatus.available.value)
        .where("geohash_5", "in", geohash_neighbors[:30])
        .stream()
    )
    return [Volunteer.from_firestore(d.id, d.to_dict()) for d in docs]


async def set_busy(volunteer_id: str, dispatch_id: str) -> None:
    await update_fields(volunteer_id, {
        "availability": AvailabilityStatus.busy.value,
        "current_dispatch_id": dispatch_id,
    })


async def set_available(volunteer_id: str) -> None:
    await update_fields(volunteer_id, {
        "availability": AvailabilityStatus.available.value,
        "current_dispatch_id": None,
    })


async def increment_stats(volunteer_id: str, hours: float) -> None:
    """Called when a mission is completed."""
    from google.cloud.firestore import Increment
    db = get_db()
    db.collection(COL_VOLUNTEERS).document(volunteer_id).update({
        "total_hours": Increment(hours),
        "completed_missions": Increment(1),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
