import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.services.gemini_ocr_service import extract_text_from_image

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intake", tags=["intake"])

MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB (Gemini inline_data limit)

MIME_MAP = {
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png":  "image/png",
    ".webp": "image/webp",
}

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/jpg",
    "image/png",
    "image/webp",
}


class ImageIntakeResponse(BaseModel):
    extracted_text: str
    confidence: float
    needs_review: bool
    language_detected: str
    image_quality: str
    text_regions: list[dict]
    illegible_regions_count: int
    confidence_indicators: dict
    file_size_bytes: int


@router.post(
    "/image",
    response_model=ImageIntakeResponse,
    status_code=status.HTTP_200_OK,
    summary="Extract text from field image via Gemini Vision",
    description=(
        "Accepts JPEG/PNG/WEBP (max 20 MB). "
        "Runs Gemini 1.5 Pro OCR with structured JSON extraction. "
        "Sets needs_review=true for blurry/low-confidence images. "
        "Retries once on timeout before flagging for manual review."
    ),
)
async def image_intake(
    file: Annotated[UploadFile, File(description="Image file (JPEG/PNG/WEBP, max 20 MB)")],
):
    # ── Validate ─────────────────────────────────────────────────────────────
    content_type, mime_type = _resolve_mime(file.filename or "", file.content_type or "")

    if mime_type is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {content_type!r}. Accepted: JPEG, PNG, WEBP",
        )

    image_bytes = await file.read()
    file_size = len(image_bytes)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file received",
        )

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size / 1024 / 1024:.1f} MB. Max 20 MB.",
        )

    logger.info(
        f"Image intake: file={file.filename!r}, size={file_size/1024:.1f}KB, "
        f"mime={mime_type}"
    )

    # ── Extract ───────────────────────────────────────────────────────────────
    try:
        result = await extract_text_from_image(image_bytes, mime_type)
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(e),
        )
    except Exception:
        logger.exception(f"Unexpected OCR error for {file.filename!r}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="OCR failed unexpectedly",
        )

    return ImageIntakeResponse(
        **result.dict(),
        file_size_bytes=file_size,
    )


def _resolve_mime(filename: str, content_type: str) -> tuple[str, str | None]:
    """
    Resolve MIME type from extension (more reliable) then content-type header.
    Returns (original_content_type, resolved_mime | None).
    """
    from pathlib import Path
    ext = Path(filename).suffix.lower()
    if ext in MIME_MAP:
        return content_type, MIME_MAP[ext]
    ct = content_type.lower().split(";")[0].strip()
    if ct in ALLOWED_CONTENT_TYPES:
        return content_type, ct
    return content_type, None