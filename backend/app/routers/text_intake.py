"""
POST /intake/text  — raw text intake channel.

Also exports the shared extraction orchestrator used by voice and image
routers after their respective transcription/OCR steps.
"""

import logging

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.extraction_service import (
    ExtractionResult,
    SourceChannel,
    extract_need_fields,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intake", tags=["intake"])


# ── Request / Response ────────────────────────────────────────────────────────

class TextIntakeRequest(BaseModel):
    text: str = Field(min_length=5, max_length=10_000, description="Raw field report text")
    language_hint: str | None = Field(
        default=None,
        description="Optional ISO 639-1 hint (hi/bn/en) — does not constrain extraction",
    )


class ExtractionResponse(BaseModel):
    need_type: str
    description_clean: str
    urgency_score: float
    urgency_reasoning: str
    affected_count: int | None
    skills_needed: list[str]
    location_text: str
    contact_name: str | None
    contact_detail: str | None
    source_channel: str
    extraction_failed: bool
    prompt_version: str


# ── Endpoint ──────────────────────────────────────────────────────────────────

@router.post(
    "/text",
    response_model=ExtractionResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract NeedCard fields from raw text report",
    description=(
        "Accepts plain text field report in any language. "
        "Returns structured NeedCard fields via Gemini extraction. "
        "On extraction failure, returns extraction_failed=True with raw input preserved."
    ),
)
async def text_intake(body: TextIntakeRequest):
    logger.info(f"Text intake: {len(body.text)} chars, lang_hint={body.language_hint!r}")

    try:
        result = await extract_need_fields(
            raw_text=body.text,
            source_channel=SourceChannel.text,
        )
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    except Exception:
        logger.exception("Unexpected extraction error")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Extraction failed unexpectedly")

    return _to_response(result)


# ── Shared helper used by voice + image routers ───────────────────────────────

async def run_extraction(
    text: str,
    source_channel: SourceChannel,
) -> ExtractionResponse:
    """
    Convenience wrapper called by voice_intake and image_intake after their
    transcription/OCR steps. Raises HTTPException on hard failure.
    """
    try:
        result = await extract_need_fields(raw_text=text, source_channel=source_channel)
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(e))
    return _to_response(result)


def _to_response(result: ExtractionResult) -> ExtractionResponse:
    return ExtractionResponse(
        need_type=result.need_type.value,
        description_clean=result.description_clean,
        urgency_score=result.urgency_score,
        urgency_reasoning=result.urgency_reasoning,
        affected_count=result.affected_count,
        skills_needed=result.skills_needed,
        location_text=result.location_text,
        contact_name=result.contact_name,
        contact_detail=result.contact_detail,
        source_channel=result.source_channel.value,
        extraction_failed=result.extraction_failed,
        prompt_version=result.prompt_version,
    )