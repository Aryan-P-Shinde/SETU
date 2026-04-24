"""
Voice channel adapter.

Accepts audio file → Whisper transcription → IntakePayload → process_intake().
The channel's only job: produce clean text. Everything else is the intake service.

Phase 5B: WhatsApp voice notes will hit whatsapp_channel.py, which downloads
the audio from Twilio, calls whisper_service directly, then calls process_intake().
Same Whisper service, different entry point.
"""

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from app.services.intake_service import IntakePayload, IntakeResult, process_intake
from app.services.whisper_service import transcribe_audio
from app.services.extraction_service import SourceChannel

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/intake", tags=["intake"])

MAX_FILE_SIZE = 25 * 1024 * 1024
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".ogg", ".webm", ".m4a"}
ALLOWED_CONTENT_TYPES = {
    "audio/wav", "audio/x-wav", "audio/mpeg", "audio/mp3",
    "audio/ogg", "audio/webm", "application/octet-stream",
}


@router.post(
    "/voice",
    response_model=IntakeResult,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a voice field report",
    description="Transcribes audio (Whisper) then runs the same intake pipeline as text.",
)
async def voice_channel(
    file: Annotated[UploadFile, File(description="WAV/MP3/OGG/WEBM, max 25 MB")],
    submitter_id: str | None = None,
):
    # ── Validate ──────────────────────────────────────────────────────────────
    ext = Path(file.filename or "").suffix.lower()
    ct = (file.content_type or "").lower()

    if ct not in ALLOWED_CONTENT_TYPES and ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported type: {ct}. Accepted: WAV, MP3, OGG, WEBM",
        )

    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty file")
    if len(audio_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail=f"Max 25 MB. Got {len(audio_bytes)/1024/1024:.1f} MB")

    # ── Transcribe → plain text ───────────────────────────────────────────────
    try:
        transcription = await transcribe_audio(audio_bytes, file.filename or "audio.wav")
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=f"Transcription unavailable: {e}")
    except Exception:
        logger.exception("Whisper failed")
        raise HTTPException(status_code=500, detail="Transcription failed")

    if not transcription.transcript.strip():
        raise HTTPException(status_code=422, detail="Audio produced empty transcript — check audio quality")

    # ── Normalise → intake service ────────────────────────────────────────────
    payload = IntakePayload(
        raw_text=transcription.transcript,
        source_channel=SourceChannel.voice,
        language_hint=transcription.language,
        submitter_id=submitter_id,
        needs_review=False,
    )

    try:
        return await process_intake(payload)
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception:
        logger.exception("Intake service failed after voice transcription")
        raise HTTPException(status_code=500, detail="Intake failed")