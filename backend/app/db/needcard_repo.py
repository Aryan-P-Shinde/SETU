"""
NeedCard repository — all Firestore operations for NeedCards.

Pattern: thin repository layer. Routers/services call these functions.
No business logic here — just reads, writes, and queries.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from app.db.firestore_client import COL_NEED_CARDS, get_db
from app.models.needcard import NeedCard, NeedStatus

logger = logging.getLogger(__name__)


async def create(card: NeedCard) -> str:
    """Write a new NeedCard. Returns the document ID."""
    db = get_db()
    doc_ref = db.collection(COL_NEED_CARDS).document(card.id)
    doc_ref.set(card.to_firestore())
    logger.info(f"NeedCard created: {card.id} type={card.need_type} urgency={card.urgency_score_eff}")
    return card.id


async def get(card_id: str) -> Optional[NeedCard]:
    """Fetch a single NeedCard by ID. Returns None if not found."""
    db = get_db()
    doc = db.collection(COL_NEED_CARDS).document(card_id).get()
    if not doc.exists:
        return None
    return NeedCard.from_firestore(doc.id, doc.to_dict())


async def update(card: NeedCard) -> None:
    """Overwrite a NeedCard document. Always call card.touch() before this."""
    card.touch()
    db = get_db()
    db.collection(COL_NEED_CARDS).document(card.id).set(card.to_firestore())


async def update_fields(card_id: str, fields: dict) -> None:
    """Partial update — only the provided fields. Automatically sets updated_at."""
    fields["updated_at"] = datetime.now(timezone.utc).isoformat()
    db = get_db()
    db.collection(COL_NEED_CARDS).document(card_id).update(fields)


async def list_open(limit: int = 50) -> list[NeedCard]:
    """
    Return open NeedCards sorted by effective urgency descending.
    Requires composite index: status ASC + urgency_score_eff DESC
    """
    db = get_db()
    docs = (
        db.collection(COL_NEED_CARDS)
        .where("status", "==", NeedStatus.open.value)
        .order_by("urgency_score_eff", direction="DESCENDING")
        .limit(limit)
        .stream()
    )
    return [NeedCard.from_firestore(d.id, d.to_dict()) for d in docs]


async def list_needs_review() -> list[NeedCard]:
    """Cards flagged for manual review — surfaced separately in admin dashboard."""
    db = get_db()
    docs = (
        db.collection(COL_NEED_CARDS)
        .where("needs_review", "==", True)
        .where("status", "==", NeedStatus.open.value)
        .stream()
    )
    return [NeedCard.from_firestore(d.id, d.to_dict()) for d in docs]


async def list_by_status(status: NeedStatus, limit: int = 100) -> list[NeedCard]:
    """Generic status filter — used by admin stats endpoint."""
    db = get_db()
    docs = (
        db.collection(COL_NEED_CARDS)
        .where("status", "==", status.value)
        .limit(limit)
        .stream()
    )
    return [NeedCard.from_firestore(d.id, d.to_dict()) for d in docs]


async def get_by_hash(source_hash: str) -> Optional[NeedCard]:
    """
    Find an existing NeedCard containing this source hash.
    Used by dedup Layer 1 (exact hash match).
    """
    db = get_db()
    docs = (
        db.collection(COL_NEED_CARDS)
        .where("source_hashes", "array_contains", source_hash)
        .where("status", "==", NeedStatus.open.value)
        .limit(1)
        .stream()
    )
    results = [NeedCard.from_firestore(d.id, d.to_dict()) for d in docs]
    return results[0] if results else None


async def find_open_in_geo_region(
    need_type: str,
    lat: float,
    lng: float,
    radius_deg: float = 0.5,   # ~55km, narrowed by haversine post-filter
) -> list[NeedCard]:
    """
    Bounding-box geo query for dedup Layer 2 (semantic dedup candidates).
    Firestore doesn't support native geo-radius; we use lat/lng bounding box
    then filter by actual distance in the dedup service.
    """
    db = get_db()
    docs = (
        db.collection(COL_NEED_CARDS)
        .where("status", "==", NeedStatus.open.value)
        .where("need_type", "==", need_type)
        .where("geo_lat", ">=", lat - radius_deg)
        .where("geo_lat", "<=", lat + radius_deg)
        .limit(50)
        .stream()
    )
    candidates = [NeedCard.from_firestore(d.id, d.to_dict()) for d in docs]
    # Secondary filter on longitude (Firestore only supports one range filter)
    return [
        c for c in candidates
        if abs(c.geo_lng - lng) <= radius_deg
    ]


async def update_urgency_scores(cards: list[tuple[str, float]]) -> None:
    """
    Batch update urgency_score_eff for the decay job.
    cards: list of (card_id, new_eff_score)
    Uses Firestore batched writes — max 500 per batch.
    """
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()

    # Chunk into batches of 500 (Firestore limit)
    for chunk_start in range(0, len(cards), 500):
        chunk = cards[chunk_start:chunk_start + 500]
        batch = db.batch()
        for card_id, new_score in chunk:
            ref = db.collection(COL_NEED_CARDS).document(card_id)
            batch.update(ref, {
                "urgency_score_eff": round(new_score, 1),
                "updated_at": now,
            })
        batch.commit()
    logger.info(f"Decay job updated urgency for {len(cards)} NeedCards")


async def mark_stale(card_ids: list[str]) -> None:
    """Bulk-mark NeedCards as stale (decay job final step)."""
    db = get_db()
    now = datetime.now(timezone.utc).isoformat()
    batch = db.batch()
    for card_id in card_ids[:500]:
        ref = db.collection(COL_NEED_CARDS).document(card_id)
        batch.update(ref, {"status": NeedStatus.stale.value, "updated_at": now})
    batch.commit()


async def update_embedding(card_id: str, embedding: list[float]) -> None:
    """
    Store the embedding vector after the async embedding job runs.
    The Firestore VECTOR type is set by passing a special sentinel value;
    the firebase_admin SDK handles this transparently for list[float].
    """
    db = get_db()
    db.collection(COL_NEED_CARDS).document(card_id).update({
        "embedding": embedding,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
