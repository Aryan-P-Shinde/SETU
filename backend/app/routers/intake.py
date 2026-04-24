import logging
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from app.services.whisper_service import transcribe_audio

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intake", tags=["intake"])

# ── Constants ────────────────────────────────────────────────────────────────
MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB per PRD
ALLOWED_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",       # MP3
    "audio/mp3",
    "audio/ogg",
    "audio/webm",       # from browser MediaRecorder
    "application/octet-stream",  # fallback when content-type is missing
}
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".webm", ".m4a"}


# ── Response model ───────────────────────────────────────────────────────────
class VoiceIntakeResponse(BaseModel):
    transcript: str
    detected_language: str
    duration_s: float
    file_size_bytes: int
    filename: str


# ── Endpoint ─────────────────────────────────────────────────────────────────
@router.post(
    "/voice",
    response_model=VoiceIntakeResponse,
    status_code=status.HTTP_200_OK,
    summary="Transcribe field audio recording",
    description=(
        "Accepts WAV/MP3/OGG/WEBM audio (max 25 MB). "
        "Returns transcript, detected language (ISO 639-1), and processing time. "
        "Handles Hindi, Bengali, English and code-switching."
    ),
)
async def voice_intake(
    file: Annotated[UploadFile, File(description="Audio file (WAV/MP3/OGG, max 25 MB)")],
):
    # ── Validate content type ────────────────────────────────────────────────
    content_type = (file.content_type or "").lower()
    ext = _get_extension(file.filename or "")

    if content_type not in ALLOWED_TYPES and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported file type: {content_type}. Accepted: WAV, MP3, OGG, WEBM",
        )

    # ── Read and size-check ──────────────────────────────────────────────────
    audio_bytes = await file.read()
    file_size = len(audio_bytes)

    if file_size == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file received",
        )

    if file_size > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail=f"File too large: {file_size / 1024 / 1024:.1f} MB. Max 25 MB.",
        )

    logger.info(
        f"Voice intake: file={file.filename!r}, size={file_size/1024:.1f}KB, "
        f"content_type={content_type}"
    )

    # ── Transcribe (temp file created + deleted inside service) ─────────────
    try:
        result = await transcribe_audio(audio_bytes, file.filename or "audio.wav")
    except RuntimeError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Transcription service unavailable: {e}",
        )
    except Exception as e:
        logger.exception(f"Transcription failed for {file.filename!r}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Transcription failed. File has been deleted.",
        )

    return VoiceIntakeResponse(
        transcript=result.transcript,
        detected_language=result.language,
        duration_s=result.duration_s,
        file_size_bytes=file_size,
        filename=file.filename or "audio.wav",
    )


def _get_extension(filename: str) -> str:
    from pathlib import Path
    return Path(filename).suffix.lower()