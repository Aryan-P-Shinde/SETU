"""
Dispatch router — Phase 2 additions.

POST /dispatch/quick            — create a dispatch for a needcard + best available volunteer
POST /admin/run-decay           — manually trigger urgency decay (replaces Cloud Scheduler for demo)
GET  /dispatch/{dispatch_id}    — get a dispatch record
POST /dispatch/{dispatch_id}/accept
POST /dispatch/{dispatch_id}/en_route
POST /dispatch/{dispatch_id}/complete
POST /dispatch/{dispatch_id}/cancel

The /dispatch/quick endpoint is the key fix: previously the brief button called
POST /brief/{dispatch_id} but no dispatch_id existed. This creates one.
"""

import logging
import math
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.db import dispatch_repo, needcard_repo, volunteer_repo
from app.models.dispatch import DispatchRecord, DispatchStatus
from app.models.needcard import NeedStatus
from app.models.volunteer import AvailabilityStatus

logger = logging.getLogger(__name__)
router = APIRouter(tags=["dispatch"])


# ── Models ────────────────────────────────────────────────────────────────────

class QuickDispatchRequest(BaseModel):
    needcard_id: str
    volunteer_id: Optional[str] = Field(
        default=None,
        description="If omitted, SETU picks the best available volunteer by proximity + skill match",
    )


class QuickDispatchResponse(BaseModel):
    dispatch_id: str
    needcard_id: str
    volunteer_id: str
    distance_km: float
    skill_overlap: list[str]
    match_score: float
    status: str


class DispatchOut(BaseModel):
    id: str
    needcard_id: str
    volunteer_id: str
    match_score: float
    distance_km: float
    skill_overlap: list[str]
    brief_text: str
    brief_status: str
    status: str
    dispatched_at: str
    accepted_at: Optional[str]
    completed_at: Optional[str]
    cancelled_at: Optional[str]
    cancellation_reason: Optional[str]


class DecayRunResponse(BaseModel):
    cards_processed: int
    cards_updated: int
    cards_staled: int
    run_at: str


# ── Quick dispatch ─────────────────────────────────────────────────────────────

@router.post(
    "/dispatch/quick",
    response_model=QuickDispatchResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a dispatch for a NeedCard — finds best volunteer or uses provided one",
)
async def quick_dispatch(body: QuickDispatchRequest):
    # Load the NeedCard
    card = await needcard_repo.get(body.needcard_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"NeedCard not found: {body.needcard_id}")
    if card.status not in (NeedStatus.open, NeedStatus.matched):
        raise HTTPException(status_code=400, detail=f"NeedCard status is {card.status.value} — cannot dispatch")

    # Check for existing active dispatch
    existing = await dispatch_repo.get_active_for_needcard(body.needcard_id)
    if existing:
        return QuickDispatchResponse(
            dispatch_id=existing.id,
            needcard_id=existing.needcard_id,
            volunteer_id=existing.volunteer_id,
            distance_km=existing.distance_km,
            skill_overlap=existing.skill_overlap,
            match_score=existing.match_score,
            status=existing.status.value,
        )

    # Resolve volunteer
    if body.volunteer_id:
        volunteer = await volunteer_repo.get(body.volunteer_id)
        if not volunteer:
            raise HTTPException(status_code=404, detail=f"Volunteer not found: {body.volunteer_id}")
    else:
        volunteer = await _find_best_volunteer(card)
        if not volunteer:
            raise HTTPException(
                status_code=503,
                detail="No available volunteers found near this NeedCard. Try again or specify a volunteer_id.",
            )

    # Compute match context
    distance_km = _haversine(card.geo_lat, card.geo_lng, volunteer.current_lat, volunteer.current_lng)
    skill_overlap = [s for s in card.skills_needed if s in volunteer.skills]
    match_score = _simple_match_score(distance_km, skill_overlap, card.skills_needed)

    # Create dispatch record
    record = DispatchRecord(
        needcard_id=body.needcard_id,
        volunteer_id=volunteer.id,
        match_score=match_score,
        distance_km=distance_km,
        skill_overlap=skill_overlap,
    )
    await dispatch_repo.create(record)

    # Mark NeedCard as matched
    card.mark_dispatched()
    await needcard_repo.update(card)

    # Mark volunteer as busy
    await volunteer_repo.set_busy(volunteer.id, record.id)

    logger.info(f"Quick dispatch created: {record.id} → volunteer={volunteer.id} need={body.needcard_id}")
    return QuickDispatchResponse(
        dispatch_id=record.id,
        needcard_id=body.needcard_id,
        volunteer_id=volunteer.id,
        distance_km=round(distance_km, 2),
        skill_overlap=skill_overlap,
        match_score=round(match_score, 3),
        status=record.status.value,
    )


# ── Admin: manual decay trigger ────────────────────────────────────────────────

@router.post(
    "/admin/run-decay",
    response_model=DecayRunResponse,
    summary="Manually trigger urgency decay — replaces Cloud Scheduler for demo/testing",
)
async def run_decay():
    """
    Decay formula (from PRD):
      urgency_score_eff = urgency_score_base * e^(-λ * hours_elapsed)
    where λ = 0.05 (half-life ~14h for base-10 cards).

    Cards with eff < 1.0 after more than 48h are staled.
    """
    LAMBDA = 0.05
    STALE_THRESHOLD = 1.0
    STALE_AFTER_HOURS = 48

    now = datetime.now(timezone.utc)
    cards = await needcard_repo.list_open(limit=500)

    updates: list[tuple[str, float]] = []
    to_stale: list[str] = []

    for card in cards:
        hours_elapsed = (now - card.created_at).total_seconds() / 3600
        new_eff = card.urgency_score_base * math.exp(-LAMBDA * hours_elapsed)
        new_eff = max(0.0, round(new_eff, 1))

        if new_eff != card.urgency_score_eff:
            if new_eff < STALE_THRESHOLD and hours_elapsed >= STALE_AFTER_HOURS:
                to_stale.append(card.id)
            else:
                updates.append((card.id, new_eff))

    if updates:
        await needcard_repo.update_urgency_scores(updates)
    if to_stale:
        await needcard_repo.mark_stale(to_stale)

    logger.info(f"Decay run: {len(updates)} updated, {len(to_stale)} staled")
    return DecayRunResponse(
        cards_processed=len(cards),
        cards_updated=len(updates),
        cards_staled=len(to_stale),
        run_at=now.isoformat(),
    )


# ── Dispatch lifecycle ─────────────────────────────────────────────────────────

@router.get("/dispatch/{dispatch_id}", response_model=DispatchOut, summary="Get dispatch record")
async def get_dispatch(dispatch_id: str):
    record = await dispatch_repo.get(dispatch_id)
    if not record:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    return _record_out(record)


@router.post("/dispatch/{dispatch_id}/accept", response_model=DispatchOut, summary="Volunteer accepts mission")
async def accept_dispatch(dispatch_id: str):
    record = await _load_dispatch(dispatch_id)
    record.touch_accepted()
    await dispatch_repo.update(record)
    return _record_out(record)


@router.post("/dispatch/{dispatch_id}/en_route", response_model=DispatchOut, summary="Volunteer en route")
async def en_route_dispatch(dispatch_id: str):
    record = await _load_dispatch(dispatch_id)
    record.status = DispatchStatus.en_route
    await dispatch_repo.update(record)
    return _record_out(record)


@router.post("/dispatch/{dispatch_id}/complete", response_model=DispatchOut, summary="Mission complete")
async def complete_dispatch(dispatch_id: str):
    record = await _load_dispatch(dispatch_id)
    record.touch_completed()
    await dispatch_repo.update(record)
    # Mark NeedCard fulfilled + release volunteer
    card = await needcard_repo.get(record.needcard_id)
    if card:
        card.mark_fulfilled()
        await needcard_repo.update(card)
    await volunteer_repo.set_available(record.volunteer_id)
    return _record_out(record)


class CancelRequest(BaseModel):
    reason: Optional[str] = None


@router.post("/dispatch/{dispatch_id}/cancel", response_model=DispatchOut, summary="Cancel dispatch")
async def cancel_dispatch(dispatch_id: str, body: CancelRequest = CancelRequest()):
    record = await _load_dispatch(dispatch_id)
    record.touch_cancelled(body.reason or "")
    await dispatch_repo.update(record)
    await volunteer_repo.set_available(record.volunteer_id)
    return _record_out(record)


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _load_dispatch(dispatch_id: str) -> DispatchRecord:
    record = await dispatch_repo.get(dispatch_id)
    if not record:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    return record


async def _find_best_volunteer(card):
    """
    Simple geo-first volunteer selection.
    Queries all available volunteers; picks closest with skill overlap, or just closest.
    """
    from app.db.firestore_client import COL_VOLUNTEERS, get_db
    from app.models.volunteer import Volunteer

    db = get_db()
    docs = (
        db.collection(COL_VOLUNTEERS)
        .where("availability", "==", AvailabilityStatus.available.value)
        .limit(100)
        .stream()
    )
    volunteers = [Volunteer.from_firestore(d.id, d.to_dict()) for d in docs]
    if not volunteers:
        return None

    def score(v):
        dist = _haversine(card.geo_lat, card.geo_lng, v.current_lat, v.current_lng)
        overlap = sum(1 for s in card.skills_needed if s in v.skills)
        # Prefer skill match, penalise distance
        return -(overlap * 10) + dist

    return min(volunteers, key=score)


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in km between two lat/lng points."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _simple_match_score(distance_km: float, skill_overlap: list[str], skills_needed: list[str]) -> float:
    geo_score = max(0.0, 1.0 - distance_km / 50.0)  # 0→1 within 50km
    if skills_needed:
        skill_score = len(skill_overlap) / len(skills_needed)
    else:
        skill_score = 1.0
    return round(0.4 * geo_score + 0.6 * skill_score, 3)


def _record_out(record: DispatchRecord) -> DispatchOut:
    return DispatchOut(
        id=record.id,
        needcard_id=record.needcard_id,
        volunteer_id=record.volunteer_id,
        match_score=record.match_score,
        distance_km=record.distance_km,
        skill_overlap=record.skill_overlap,
        brief_text=record.brief_text,
        brief_status=record.brief_status,
        status=record.status.value,
        dispatched_at=record.dispatched_at.isoformat(),
        accepted_at=record.accepted_at.isoformat() if record.accepted_at else None,
        completed_at=record.completed_at.isoformat() if record.completed_at else None,
        cancelled_at=record.cancelled_at.isoformat() if record.cancelled_at else None,
        cancellation_reason=record.cancellation_reason,
    )
