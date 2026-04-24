"""
Whisper transcription service.

Model size trade-off (documented as per PRD risk note):
┌──────────┬──────────┬───────────┬──────────────────────────────────────┐
│ Model    │ Size     │ WER (en)  │ Recommendation                       │
├──────────┼──────────┼───────────┼──────────────────────────────────────┤
│ base     │ ~140 MB  │ ~8%       │ Demo / Cloud Run (CPU) ✅             │
│ small    │ ~460 MB  │ ~5%       │ Better accuracy, still CPU-feasible  │
│ medium   │ ~1.5 GB  │ ~3%       │ Needs 4 GB RAM                       │
│ large-v3 │ ~2.9 GB  │ ~2%       │ Production with GPU only             │
└──────────┴──────────┴───────────┴──────────────────────────────────────┘

Strategy:
  1. Try local Whisper (model loaded at startup, zero latency after warm-up)
  2. Fall back to OpenAI Whisper API if local model unavailable (no GPU / OOM)

Set WHISPER_MODE=local | api in .env
Set WHISPER_MODEL=base | small | medium | large-v3
"""

import io
import logging
import os
import tempfile
import time
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Lazy imports so the app boots even if whisper isn't installed ──
_local_model = None
_local_model_loaded = False


def _get_local_model():
    """Load Whisper model once and cache it (lazy, thread-safe enough for single worker)."""
    global _local_model, _local_model_loaded
    if _local_model_loaded:
        return _local_model
    try:
        import whisper  # openai-whisper

        from app.core.config import settings
        model_name = settings.whisper_model
        logger.info(f"Loading Whisper model: {model_name}")
        _local_model = whisper.load_model(model_name)
        logger.info(f"Whisper {model_name} loaded successfully")
    except Exception as e:
        logger.warning(f"Local Whisper unavailable ({e}), will use API fallback")
        _local_model = None
    finally:
        _local_model_loaded = True
    return _local_model


class TranscriptionResult:
    def __init__(self, transcript: str, language: str, duration_s: float):
        self.transcript = transcript
        self.language = language
        self.duration_s = duration_s

    def dict(self):
        return {
            "transcript": self.transcript,
            "detected_language": self.language,
            "duration_s": round(self.duration_s, 2),
        }


async def transcribe_audio(audio_bytes: bytes, filename: str) -> TranscriptionResult:
    """
    Transcribe audio bytes.
    Tries local Whisper first, falls back to OpenAI API.
    Temp file is always deleted after transcription.
    """
    from app.core.config import settings
    mode = settings.whisper_mode

    # Write to temp file (Whisper needs a file path, not raw bytes)
    suffix = Path(filename).suffix.lower() or ".wav"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(audio_bytes)
        tmp_path = tmp.name

    try:
        if mode == "local":
            return await _transcribe_local(tmp_path)
        else:
            return await _transcribe_api(tmp_path, audio_bytes, filename)
    finally:
        # Always clean up, even on exception
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


async def _transcribe_local(tmp_path: str) -> TranscriptionResult:
    """Run local Whisper model."""
    model = _get_local_model()
    if model is None:
        raise RuntimeError("Local Whisper model not available. Set WHISPER_MODE=api")

    start = time.perf_counter()

    # Whisper transcribe is CPU-bound; run synchronously (wrap in threadpool for prod)
    result = model.transcribe(
        tmp_path,
        task="transcribe",
        # Don't force language — let Whisper detect it (handles Hindi/Bengali/English)
        language=None,
        # Temperature 0 = greedy, most deterministic
        temperature=0,
        # Compression ratio filter to catch garbage transcriptions
        compression_ratio_threshold=2.4,
        logprob_threshold=-1.0,
        no_speech_threshold=0.6,
        # Word-level timestamps useful for future features
        word_timestamps=False,
    )

    elapsed = time.perf_counter() - start
    logger.info(f"Local Whisper transcribed in {elapsed:.2f}s, lang={result['language']}")

    return TranscriptionResult(
        transcript=result["text"].strip(),
        language=result["language"],
        duration_s=elapsed,
    )


async def _transcribe_api(
    tmp_path: str, audio_bytes: bytes, filename: str
) -> TranscriptionResult:
    """Fall back to OpenAI Whisper API."""
    import httpx

    from app.core.config import settings
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set and local Whisper unavailable")

    start = time.perf_counter()

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            "https://api.openai.com/v1/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            files={"file": (filename, io.BytesIO(audio_bytes), "audio/mpeg")},
            data={"model": "whisper-1", "response_format": "verbose_json"},
        )
        resp.raise_for_status()
        data = resp.json()

    elapsed = time.perf_counter() - start
    lang = data.get("language", "unknown")
    logger.info(f"API Whisper transcribed in {elapsed:.2f}s, lang={lang}")

    return TranscriptionResult(
        transcript=data.get("text", "").strip(),
        language=lang,
        duration_s=elapsed,
    )