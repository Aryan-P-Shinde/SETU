"""
Tests for POST /api/v1/intake/voice

Uses mocks so CI doesn't need Whisper installed.
Real Whisper integration tests live in tests/integration/ (run locally).
"""

import io
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.whisper_service import TranscriptionResult

# ── Helpers ──────────────────────────────────────────────────────────────────
def _make_audio_file(content: bytes = b"fake-audio", filename: str = "test.wav"):
    return {"file": (filename, io.BytesIO(content), "audio/wav")}


MOCK_RESULT = TranscriptionResult(
    transcript="पंद्रह लोगों को खाने की जरूरत है",  # Hindi: 15 people need food
    language="hi",
    duration_s=1.23,
)


# ── Tests ─────────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_voice_intake_success():
    with patch(
        "app.routers.intake.transcribe_audio",
        new_callable=AsyncMock,
        return_value=MOCK_RESULT,
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/intake/voice", files=_make_audio_file())

    assert resp.status_code == 200
    data = resp.json()
    assert data["transcript"] == MOCK_RESULT.transcript
    assert data["detected_language"] == "hi"
    assert data["duration_s"] == 1.23
    assert data["file_size_bytes"] == len(b"fake-audio")


@pytest.mark.asyncio
async def test_voice_intake_empty_file():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/intake/voice", files=_make_audio_file(content=b""))
    assert resp.status_code == 400
    assert "Empty" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_voice_intake_file_too_large():
    big = b"x" * (26 * 1024 * 1024)  # 26 MB
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/intake/voice", files=_make_audio_file(content=big))
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_voice_intake_unsupported_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/intake/voice",
            files={"file": ("test.pdf", io.BytesIO(b"not audio"), "application/pdf")},
        )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_voice_intake_service_unavailable():
    with patch(
        "app.routers.intake.transcribe_audio",
        new_callable=AsyncMock,
        side_effect=RuntimeError("Model not loaded"),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/intake/voice", files=_make_audio_file())
    assert resp.status_code == 503


@pytest.mark.asyncio
async def test_voice_intake_english():
    mock = TranscriptionResult("20 families stranded near the bridge", "en", 0.8)
    with patch("app.routers.intake.transcribe_audio", new_callable=AsyncMock, return_value=mock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/voice",
                files=_make_audio_file(filename="field_recording.mp3"),
            )
    assert resp.status_code == 200
    assert resp.json()["detected_language"] == "en"


@pytest.mark.asyncio
async def test_voice_intake_bengali():
    mock = TranscriptionResult("বন্যায় ৫০ জন আটকে পড়েছে", "bn", 1.1)  # Bengali
    with patch("app.routers.intake.transcribe_audio", new_callable=AsyncMock, return_value=mock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/intake/voice", files=_make_audio_file())
    assert resp.status_code == 200
    assert resp.json()["detected_language"] == "bn"


@pytest.mark.asyncio
async def test_voice_intake_webm_from_browser():
    """Browser MediaRecorder sends webm — must be accepted."""
    mock = TranscriptionResult("Need medical help urgently", "en", 0.5)
    with patch("app.routers.intake.transcribe_audio", new_callable=AsyncMock, return_value=mock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/voice",
                files={"file": ("recording.webm", io.BytesIO(b"webm-data"), "audio/webm")},
            )
    assert resp.status_code == 200