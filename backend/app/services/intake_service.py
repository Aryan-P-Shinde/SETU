"""
Intake service — channel-agnostic core engine.

All submission channels (dashboard form, WhatsApp webhook, field worker PWA)
normalise their input into an IntakePayload and call process_intake().
The result is a NeedCard written to Firestore.

Flow:
  IntakePayload
      └── extract_need_fields()       [Gemini: text → structured fields]
      └── geocode()                   [Google Maps: location_text → lat/lng]
      └── NeedCard.from_extraction()  [assemble model]
      └── dedup check                 [hash + semantic — Phase 1: hash only]
      └── needcard_repo.create()      [write to Firestore]
      └── IntakeResult

Channels are thin wrappers that:
  1. Accept channel-specific input (audio file, image bytes, raw text)
  2. Convert to plain text (Whisper / Gemini OCR / passthrough)
  3. Build an IntakePayload
  4. Call process_intake()
  5. Return IntakeResult to their caller

Adding WhatsApp in Phase 5B = write a new channel adapter, zero changes here.
"""

import hashlib
import logging
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from app.services.extraction_service import SourceChannel, extract_need_fields
from app.models.needcard import NeedCard

logger = logging.getLogger(__name__)


# ── Normalised input contract ─────────────────────────────────────────────────

class IntakePayload(BaseModel):
    """
    The single contract every channel must fulfil.
    Channels produce this; the intake service consumes it.
    """
    raw_text: str = Field(min_length=1, description="Plain text — transcript, OCR output, or typed text")
    source_channel: SourceChannel = SourceChannel.text
    language_hint: Optional[str] = None          # ISO 639-1, informational only
    needs_review: bool = False                    # channel sets True for low-confidence OCR
    submitter_id: Optional[str] = None           # Firebase UID of submitting field worker


# ── Result contract ───────────────────────────────────────────────────────────

class IntakeResult(BaseModel):
    needcard_id: str
    is_duplicate: bool = False
    merged_into: Optional[str] = None            # ID of existing card if merged
    extraction_failed: bool = False
    needs_review: bool = False
    urgency_score: float
    need_type: str


# ── Core engine ───────────────────────────────────────────────────────────────

async def process_intake(payload: IntakePayload) -> IntakeResult:
    """
    Channel-agnostic intake pipeline.
    Called by every channel adapter after normalising input.
    """
    logger.info(
        f"Intake: channel={payload.source_channel.value} "
        f"chars={len(payload.raw_text)} review={payload.needs_review}"
    )

    # ── Step 1: Extract structured fields via Gemini ──────────────────────────
    extraction = await extract_need_fields(
        raw_text=payload.raw_text,
        source_channel=payload.source_channel,
    )

    # ── Step 2: Geocode location_text → lat/lng ───────────────────────────────
    # Phase 1: geo stubbed (Step 5 of PRD builds this out)
    geo_lat, geo_lng, geo_confidence = 0.0, 0.0, 0.0
    location_text = extraction.location_text or ""
    if location_text:
        try:
            from app.services.geo_service import geocode
            geo_lat, geo_lng, geo_confidence = await geocode(location_text)
        except Exception as e:
            logger.warning(f"Geocoding failed for {location_text!r}: {e}")

    # ── Step 3: Compute source hash for dedup Layer 1 ─────────────────────────
    source_hash = _hash_text(extraction.description_clean)

    # ── Step 4: Dedup check (Layer 1 — exact hash) ────────────────────────────
    # Phase 1: hash dedup only. Semantic dedup (Layer 2) added in Step 6.
    existing_id = await _check_exact_duplicate(source_hash, extraction.need_type.value)
    if existing_id:
        logger.info(f"Exact duplicate detected → merging into {existing_id}")
        await _merge_into_existing(existing_id, source_hash, extraction.urgency_score)
        return IntakeResult(
            needcard_id=existing_id,
            is_duplicate=True,
            merged_into=existing_id,
            extraction_failed=extraction.extraction_failed,
            needs_review=payload.needs_review,
            urgency_score=extraction.urgency_score,
            need_type=extraction.need_type.value,
        )

    # ── Step 5: Build NeedCard ────────────────────────────────────────────────
    card = NeedCard.from_extraction(
        extraction_dict=extraction.dict_for_needcard(),
        geo_lat=geo_lat,
        geo_lng=geo_lng,
        geo_confidence=geo_confidence,
        source_hash=source_hash,
        needs_review=payload.needs_review or extraction.extraction_failed,
    )

    # ── Step 6: Write to Firestore ────────────────────────────────────────────
    try:
        from app.db import needcard_repo
        await needcard_repo.create(card)
    except Exception as e:
        logger.error(f"Firestore write failed: {e}")
        # Still return the card ID — caller gets a result, ops team handles persistence
        logger.warning(f"NeedCard {card.id} not persisted — returning in-memory result")

    return IntakeResult(
        needcard_id=card.id,
        is_duplicate=False,
        extraction_failed=extraction.extraction_failed,
        needs_review=card.needs_review,
        urgency_score=card.urgency_score_eff,
        need_type=card.need_type.value,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash_text(text: str) -> str:
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode()).hexdigest()


async def _check_exact_duplicate(source_hash: str, need_type: str) -> Optional[str]:
    """Return existing NeedCard ID if hash already exists, else None."""
    try:
        from app.db import needcard_repo
        existing = await needcard_repo.get_by_hash(source_hash)
        if existing and existing.need_type.value == need_type:
            return existing.id
    except Exception as e:
        logger.warning(f"Dedup check failed (non-fatal): {e}")
    return None


async def _merge_into_existing(card_id: str, new_hash: str, new_urgency: float) -> None:
    """Increment report_count and escalate urgency on the existing card."""
    try:
        from app.db import needcard_repo
        card = await needcard_repo.get(card_id)
        if card:
            card.report_count += 1
            if new_hash not in card.source_hashes:
                card.source_hashes.append(new_hash)
            if new_urgency > card.urgency_score_base:
                card.urgency_score_base = new_urgency
                card.urgency_score_eff = new_urgency
            await needcard_repo.update(card)
    except Exception as e:
        logger.warning(f"Merge update failed (non-fatal): {e}")