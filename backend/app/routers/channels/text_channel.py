"""
Text channel adapter.

Accepts raw typed text (dashboard textarea, API call).
Normalises → IntakePayload → process_intake().

Phase 5B: WhatsApp text messages will hit a separate whatsapp_channel.py
that normalises the Twilio webhook payload and calls process_intake() the same way.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.intake_service import IntakePayload, IntakeResult, process_intake
from app.services.extraction_service import SourceChannel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intake", tags=["intake"])


class TextSubmission(BaseModel):
    text: str = Field(min_length=5, max_length=10_000)
    language_hint: str | None = None
    submitter_id: str | None = None


@router.post(
    "/text",
    response_model=IntakeResult,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a text field report",
    description="Dashboard textarea or API. Text is extracted → geocoded → NeedCard created.",
)
async def text_channel(body: TextSubmission):
    payload = IntakePayload(
        raw_text=body.text,
        source_channel=SourceChannel.text,
        language_hint=body.language_hint,
        submitter_id=body.submitter_id,
        needs_review=False,
    )
    try:
        return await process_intake(payload)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception:
        logger.exception("Text channel unexpected error")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Intake failed")