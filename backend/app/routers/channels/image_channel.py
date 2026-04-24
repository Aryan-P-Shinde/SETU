"""
Image channel adapter.

Accepts image file → Gemini OCR → IntakePayload → process_intake().
Sets needs_review=True when OCR confidence is low — surfaces card in admin dashboard.

Phase 5B: WhatsApp images will hit whatsapp_channel.py, which downloads
the image from Twilio media URL, calls gemini_ocr_service directly, then
calls process_intake(). Same OCR service, different entry point.
"""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.services.intake_service import IntakePayload, IntakeResult, process_intake
from app.services.gemini_ocr_service import extract_text_from_image
from app.services.extraction_service import SourceChannel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intake", tags=["intake"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # Gemini inline_data limit

MIME_MAP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png",  ".webp": "image/webp",
}
ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/jpg", "image/png", "image/webp"}

# Confidence below this → needs_review flag set on NeedCard
OCR_REVIEW_THRESHOLD = 0.6


@router.post(
    "/image",
    response_model=IntakeResult,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a field image (handwritten form / WhatsApp screenshot)",
    description=(
        "OCRs image via Gemini Vision then runs the same intake pipeline as text. "
        "Low-confidence images set needs_review=True on the resulting NeedCard."
    ),
)
async def image_channel(
    file: Annotated[UploadFile, File(description="JPEG/PNG/WEBP, max 20 MB")],
    submitter_id: str | None = None,
):
    # ── Validate ──────────────────────────────────────────────────────────────
    ext = Path(file.filename or "").suffix.lower()
    ct = (file.content_type or "").lower().split(";")[0].strip()
    mime_type = MIME_MAP.get(ext) or (ct if ct in ALLOWED_CONTENT_TYPES else None)

    if mime_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported type: {ct}. Accepted: JPEG, PNG, WEBP",
        )

    image_bytes = await file.read()
    if not image_bytes:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(image_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"Max 20 MB. Got {len(image_bytes)/1024/1024:.1f} MB")

    # ── OCR → plain text ──────────────────────────────────────────────────────
    try:
        ocr = await extract_text_from_image(image_bytes, mime_type)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        logger.exception("OCR failed")
        raise HTTPException(status_code=500, detail="OCR failed")

    if not ocr.extracted_text.strip():
        raise HTTPException(status_code=422, detail="Image produced no readable text")

    # ── Normalise → intake service ────────────────────────────────────────────
    needs_review = ocr.needs_review or (ocr.confidence < OCR_REVIEW_THRESHOLD)

    payload = IntakePayload(
        raw_text=ocr.extracted_text,
        source_channel=SourceChannel.image,
        language_hint=ocr.language,
        submitter_id=submitter_id,
        needs_review=needs_review,
    )

    try:
        return await process_intake(payload)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        logger.exception("Intake service failed after OCR")
        raise HTTPException(status_code=500, detail="Intake failed")