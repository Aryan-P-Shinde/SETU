"""
GET /needcards  — list NeedCards with optional status filter.

This endpoint was architecturally present (listOpenNeedCards() in api.ts)
but the router was never registered. This wires it up.
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel

from app.db import needcard_repo
from app.models.needcard import NeedCard, NeedStatus

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/needcards", tags=["needcards"])


class NeedCardOut(BaseModel):
    id: str
    need_type: str
    description_clean: str
    urgency_score_base: float
    urgency_score_eff: float
    urgency_reasoning: str
    affected_count: Optional[int]
    skills_needed: list[str]
    geo_lat: float
    geo_lng: float
    geo_confidence: float
    location_text_raw: str
    contact_name: Optional[str]
    contact_detail: Optional[str]
    report_count: int
    status: str
    needs_review: bool
    extraction_failed: bool
    created_at: str
    updated_at: str


def _card_to_out(card: NeedCard) -> NeedCardOut:
    return NeedCardOut(
        id=card.id,
        need_type=card.need_type.value,
        description_clean=card.description_clean,
        urgency_score_base=card.urgency_score_base,
        urgency_score_eff=card.urgency_score_eff,
        urgency_reasoning=card.urgency_reasoning,
        affected_count=card.affected_count,
        skills_needed=card.skills_needed,
        geo_lat=card.geo_lat,
        geo_lng=card.geo_lng,
        geo_confidence=card.geo_confidence,
        location_text_raw=card.location_text_raw,
        contact_name=card.contact_name,
        contact_detail=card.contact_detail,
        report_count=card.report_count,
        status=card.status.value,
        needs_review=card.needs_review,
        extraction_failed=card.extraction_failed,
        created_at=card.created_at.isoformat(),
        updated_at=card.updated_at.isoformat(),
    )


@router.get(
    "",
    response_model=list[NeedCardOut],
    summary="List NeedCards with optional status filter",
)
async def list_needcards(
    status: Optional[str] = Query(default="open", description="Filter by status: open|fulfilled|stale|matched"),
    limit: int = Query(default=50, le=200),
):
    try:
        need_status = NeedStatus(status) if status else NeedStatus.open
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")

    try:
        if need_status == NeedStatus.open:
            cards = await needcard_repo.list_open(limit=limit)
        else:
            cards = await needcard_repo.list_by_status(need_status, limit=limit)
        return [_card_to_out(c) for c in cards]
    except Exception as e:
        logger.exception("Failed to list needcards")
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/{card_id}",
    response_model=NeedCardOut,
    summary="Get a single NeedCard by ID",
)
async def get_needcard(card_id: str):
    card = await needcard_repo.get(card_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"NeedCard not found: {card_id}")
    return _card_to_out(card)
