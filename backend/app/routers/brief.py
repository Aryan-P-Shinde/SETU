"""
Brief endpoints — Phase 4 Step 2.

POST   /brief/{dispatch_id}          — generate brief, store in dispatch_log
GET    /brief/{dispatch_id}          — fetch brief + map link
PATCH  /brief/{dispatch_id}          — NGO edit (stores diff for fine-tuning)
POST   /brief/{dispatch_id}/approve  — NGO approves (draft → approved)
POST   /brief/{dispatch_id}/send     — send approved brief to volunteer via FCM

State machine:
  [not generated] → draft → approved → sent
                       ↑ edit always resets to draft

PRD response shape: {brief_text, map_link, created_at}  (plus extras for frontend)
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.brief_service import generate_brief
from app.services.delivery_service import deliver_brief
from app.db import dispatch_repo, needcard_repo, volunteer_repo

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/brief", tags=["brief"])


# ── Models ────────────────────────────────────────────────────────────────────

class BriefResponse(BaseModel):
    dispatch_id: str
    brief_text: str
    brief_status: str          # draft | approved | sent
    map_link: str | None       # Google Maps deep link
    created_at: str            # ISO8601 — dispatch creation time
    language: str
    word_count: int
    generation_failed: bool


class BriefSentResponse(BriefResponse):
    delivery_success: bool
    delivery_channel: str
    delivery_error: str | None = None


class BriefEditRequest(BaseModel):
    edited_text: str = Field(min_length=20, max_length=2000)
    editor_note: str | None = None


# ── Generate ──────────────────────────────────────────────────────────────────

@router.post(
    "/{dispatch_id}",
    response_model=BriefResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate volunteer mission brief",
)
async def create_brief(dispatch_id: str):
    dispatch, card, volunteer = await _load_ctx(dispatch_id)

    result = await generate_brief(
        needcard_dict=card.to_brief_context(),
        volunteer_skills=volunteer.skills,
        language_pref=volunteer.language_pref,
    )

    dispatch.brief_text = result.brief_text
    dispatch.brief_status = "draft"
    await dispatch_repo.update(dispatch)

    logger.info(f"Brief generated: dispatch={dispatch_id} words={result.word_count} failed={result.generation_failed}")

    return _resp(dispatch_id, dispatch.brief_text, "draft",
                 card, dispatch.dispatched_at, result.language,
                 result.generation_failed)


# ── Fetch ─────────────────────────────────────────────────────────────────────

@router.get("/{dispatch_id}", response_model=BriefResponse, summary="Fetch existing brief")
async def get_brief(dispatch_id: str):
    dispatch = await dispatch_repo.get(dispatch_id)
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if not dispatch.brief_text:
        raise HTTPException(status_code=404, detail="Brief not yet generated — POST /brief/{id}")

    card = await needcard_repo.get(dispatch.needcard_id)
    return _resp(dispatch_id, dispatch.brief_text, dispatch.brief_status,
                 card, dispatch.dispatched_at, "en",
                 "[Brief generation failed" in dispatch.brief_text)


# ── Edit ──────────────────────────────────────────────────────────────────────

@router.patch("/{dispatch_id}", response_model=BriefResponse, summary="NGO edits brief")
async def edit_brief(dispatch_id: str, body: BriefEditRequest):
    dispatch = await dispatch_repo.get(dispatch_id)
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if dispatch.brief_status == "sent":
        raise HTTPException(status_code=400, detail="Brief already sent — cannot edit")

    dispatch.brief_edit_history.append({
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "original": dispatch.brief_text,
        "edited": body.edited_text,
        "note": body.editor_note,
    })
    dispatch.brief_text = body.edited_text
    dispatch.brief_status = "draft"    # always reset — must re-approve after any edit
    await dispatch_repo.update(dispatch)

    card = await needcard_repo.get(dispatch.needcard_id)
    logger.info(f"Brief edited: dispatch={dispatch_id}")
    return _resp(dispatch_id, body.edited_text, "draft", card, dispatch.dispatched_at, "en", False)


# ── Approve ───────────────────────────────────────────────────────────────────

@router.post("/{dispatch_id}/approve", response_model=BriefResponse, summary="NGO approves brief")
async def approve_brief(dispatch_id: str):
    dispatch = await dispatch_repo.get(dispatch_id)
    if not dispatch:
        raise HTTPException(status_code=404, detail="Dispatch not found")
    if not dispatch.brief_text or "[Brief generation failed" in dispatch.brief_text:
        raise HTTPException(status_code=400, detail="Cannot approve a failed brief — edit it first")
    if dispatch.brief_status == "sent":
        raise HTTPException(status_code=400, detail="Brief already sent")

    dispatch.brief_status = "approved"
    await dispatch_repo.update(dispatch)

    card = await needcard_repo.get(dispatch.needcard_id)
    logger.info(f"Brief approved: dispatch={dispatch_id}")
    return _resp(dispatch_id, dispatch.brief_text, "approved", card, dispatch.dispatched_at, "en", False)


# ── Send ──────────────────────────────────────────────────────────────────────

@router.post(
    "/{dispatch_id}/send",
    response_model=BriefSentResponse,
    summary="Send approved brief to volunteer (FCM push)",
    description=(
        "Delivers via Firebase Cloud Messaging. Brief must be approved. "
        "Marks status=sent regardless of push result — volunteer sees it on next app open."
    ),
)
async def send_brief(dispatch_id: str):
    dispatch, card, volunteer = await _load_ctx(dispatch_id)

    if dispatch.brief_status != "approved":
        raise HTTPException(
            status_code=400,
            detail=f"Brief must be approved before sending. Status: {dispatch.brief_status}",
        )

    map_link = _map_link(card) if card.geo_confidence > 0.3 else None

    # ── FCM delivery (V1.1: add WhatsApp fallback here) ───────────────────────
    delivery = await deliver_brief(
        brief_text=dispatch.brief_text,
        map_link=map_link,
        volunteer_id=volunteer.id,
        dispatch_id=dispatch_id,
        fcm_token=getattr(volunteer, "fcm_token", None),
    )

    # Always mark sent — brief visible in-app on next open even if push failed
    dispatch.brief_status = "sent"
    await dispatch_repo.update(dispatch)

    level = logger.info if delivery.success else logger.warning
    level(f"Brief send: dispatch={dispatch_id} success={delivery.success} error={delivery.error}")

    return BriefSentResponse(
        dispatch_id=dispatch_id,
        brief_text=dispatch.brief_text,
        brief_status="sent",
        map_link=map_link,
        created_at=dispatch.dispatched_at.isoformat(),
        language="en",
        word_count=len(dispatch.brief_text.split()),
        generation_failed=False,
        delivery_success=delivery.success,
        delivery_channel=delivery.channel.value,
        delivery_error=delivery.error,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _load_ctx(dispatch_id: str):
    dispatch = await dispatch_repo.get(dispatch_id)
    if not dispatch:
        raise HTTPException(status_code=404, detail=f"Dispatch not found: {dispatch_id}")
    card = await needcard_repo.get(dispatch.needcard_id)
    if not card:
        raise HTTPException(status_code=404, detail=f"NeedCard not found: {dispatch.needcard_id}")
    volunteer = await volunteer_repo.get(dispatch.volunteer_id)
    if not volunteer:
        raise HTTPException(status_code=404, detail=f"Volunteer not found: {dispatch.volunteer_id}")
    return dispatch, card, volunteer


def _map_link(card) -> str:
    return f"https://maps.google.com/?q={card.geo_lat},{card.geo_lng}&zoom=17"


def _resp(dispatch_id, brief_text, brief_status, card, dispatched_at, language, generation_failed):
    return BriefResponse(
        dispatch_id=dispatch_id,
        brief_text=brief_text,
        brief_status=brief_status,
        map_link=_map_link(card) if card and card.geo_confidence > 0.3 else None,
        created_at=dispatched_at.isoformat(),
        language=language,
        word_count=len(brief_text.split()),
        generation_failed=generation_failed,
    )