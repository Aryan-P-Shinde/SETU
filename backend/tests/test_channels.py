"""
Tests for the refactored channel adapters.

Each test verifies:
  1. The channel correctly normalises input
  2. The channel calls process_intake() with the right IntakePayload
  3. The response is IntakeResult (not the old channel-specific response)

Intake service itself is always mocked here — it has its own test file.
"""

import io
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.intake_service import IntakeResult
from app.services.extraction_service import SourceChannel
from app.services.whisper_service import TranscriptionResult

INTAKE_SERVICE = "app.routers.channels.{channel}.process_intake"

MOCK_RESULT = IntakeResult(
    needcard_id="nc-test-uuid-001",
    is_duplicate=False,
    extraction_failed=False,
    needs_review=False,
    urgency_score=7.5,
    need_type="food",
)

DUPLICATE_RESULT = IntakeResult(
    needcard_id="nc-existing-001",
    is_duplicate=True,
    merged_into="nc-existing-001",
    extraction_failed=False,
    needs_review=False,
    urgency_score=7.5,
    need_type="food",
)


# ── Text channel ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_text_channel_success():
    with patch(INTAKE_SERVICE.format(channel="text_channel"),
               new_callable=AsyncMock, return_value=MOCK_RESULT):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/text",
                json={"text": "40 families need food in Ward 12. Contact Ramesh at 9876543210."},
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["needcard_id"] == "nc-test-uuid-001"
    assert data["is_duplicate"] is False
    assert data["need_type"] == "food"


@pytest.mark.asyncio
async def test_text_channel_too_short():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/intake/text", json={"text": "hi"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_text_channel_duplicate_returns_merged():
    with patch(INTAKE_SERVICE.format(channel="text_channel"),
               new_callable=AsyncMock, return_value=DUPLICATE_RESULT):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/text",
                json={"text": "40 families need food in Ward 12. Contact Ramesh at 9876543210."},
            )

    assert resp.status_code == 201
    data = resp.json()
    assert data["is_duplicate"] is True
    assert data["merged_into"] == "nc-existing-001"


@pytest.mark.asyncio
async def test_text_channel_passes_submitter_id():
    captured = {}

    async def capture(payload):
        captured["submitter_id"] = payload.submitter_id
        return MOCK_RESULT

    with patch(INTAKE_SERVICE.format(channel="text_channel"), side_effect=capture):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post(
                "/api/v1/intake/text",
                json={"text": "Flood victims need water urgently near the bridge.", "submitter_id": "field-worker-uid-123"},
            )

    assert captured["submitter_id"] == "field-worker-uid-123"


# ── Voice channel ─────────────────────────────────────────────────────────────

MOCK_TRANSCRIPT = TranscriptionResult(
    transcript="40 families need food in Ward 12",
    language="hi",
    duration_s=3.2,
)


@pytest.mark.asyncio
async def test_voice_channel_success():
    with (
        patch("app.routers.channels.voice_channel.transcribe_audio",
              new_callable=AsyncMock, return_value=MOCK_TRANSCRIPT),
        patch(INTAKE_SERVICE.format(channel="voice_channel"),
              new_callable=AsyncMock, return_value=MOCK_RESULT),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/voice",
                files={"file": ("report.wav", io.BytesIO(b"fake-audio"), "audio/wav")},
            )

    assert resp.status_code == 201
    assert resp.json()["needcard_id"] == "nc-test-uuid-001"


@pytest.mark.asyncio
async def test_voice_channel_sets_source_channel_voice():
    captured = {}

    async def capture(payload):
        captured["channel"] = payload.source_channel
        return MOCK_RESULT

    with (
        patch("app.routers.channels.voice_channel.transcribe_audio",
              new_callable=AsyncMock, return_value=MOCK_TRANSCRIPT),
        patch(INTAKE_SERVICE.format(channel="voice_channel"), side_effect=capture),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post(
                "/api/v1/intake/voice",
                files={"file": ("report.wav", io.BytesIO(b"fake-audio"), "audio/wav")},
            )

    assert captured["channel"] == SourceChannel.voice


@pytest.mark.asyncio
async def test_voice_channel_empty_file():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/intake/voice",
            files={"file": ("empty.wav", io.BytesIO(b""), "audio/wav")},
        )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_voice_channel_empty_transcript_rejected():
    empty = TranscriptionResult(transcript="   ", language="en", duration_s=1.0)
    with patch("app.routers.channels.voice_channel.transcribe_audio",
               new_callable=AsyncMock, return_value=empty):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/voice",
                files={"file": ("silent.wav", io.BytesIO(b"fake-audio"), "audio/wav")},
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_voice_channel_wrong_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/intake/voice",
            files={"file": ("doc.pdf", io.BytesIO(b"pdf-data"), "application/pdf")},
        )
    assert resp.status_code == 415


# ── Image channel ─────────────────────────────────────────────────────────────

from app.services.gemini_ocr_service import OCRResult


def _mock_ocr(confidence=0.9, needs_review=False, text="50 families need water near Mirpur Block D"):
    return OCRResult(
        extracted_text=text,
        confidence=confidence,
        needs_review=needs_review,
        language="en",
        image_quality="clear",
        text_regions=[],
        illegible_count=0,
        confidence_indicators={},
        raw_response="{}",
    )


@pytest.mark.asyncio
async def test_image_channel_success():
    with (
        patch("app.routers.channels.image_channel.extract_text_from_image",
              new_callable=AsyncMock, return_value=_mock_ocr()),
        patch(INTAKE_SERVICE.format(channel="image_channel"),
              new_callable=AsyncMock, return_value=MOCK_RESULT),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/image",
                files={"file": ("form.jpg", io.BytesIO(b"fake-jpeg"), "image/jpeg")},
            )

    assert resp.status_code == 201
    assert resp.json()["needcard_id"] == "nc-test-uuid-001"


@pytest.mark.asyncio
async def test_image_channel_low_confidence_sets_needs_review():
    """Low OCR confidence → needs_review=True passed to intake service."""
    captured = {}

    async def capture(payload):
        captured["needs_review"] = payload.needs_review
        return MOCK_RESULT

    with (
        patch("app.routers.channels.image_channel.extract_text_from_image",
              new_callable=AsyncMock, return_value=_mock_ocr(confidence=0.3, needs_review=True)),
        patch(INTAKE_SERVICE.format(channel="image_channel"), side_effect=capture),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post(
                "/api/v1/intake/image",
                files={"file": ("blurry.jpg", io.BytesIO(b"fake"), "image/jpeg")},
            )

    assert captured["needs_review"] is True


@pytest.mark.asyncio
async def test_image_channel_empty_ocr_rejected():
    """If OCR produces no text → 422, not a NeedCard with empty description."""
    empty_ocr = _mock_ocr(text="   ")
    with patch("app.routers.channels.image_channel.extract_text_from_image",
               new_callable=AsyncMock, return_value=empty_ocr):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/image",
                files={"file": ("blank.png", io.BytesIO(b"fake"), "image/png")},
            )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_image_channel_wrong_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/intake/image",
            files={"file": ("audio.mp3", io.BytesIO(b"fake"), "audio/mpeg")},
        )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_image_channel_sets_source_channel_image():
    captured = {}

    async def capture(payload):
        captured["channel"] = payload.source_channel
        return MOCK_RESULT

    with (
        patch("app.routers.channels.image_channel.extract_text_from_image",
              new_callable=AsyncMock, return_value=_mock_ocr()),
        patch(INTAKE_SERVICE.format(channel="image_channel"), side_effect=capture),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            await ac.post(
                "/api/v1/intake/image",
                files={"file": ("form.png", io.BytesIO(b"fake"), "image/png")},
            )

    assert captured["channel"] == SourceChannel.image


# ── Intake service unit tests ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_intake_service_full_pipeline():
    """Smoke test: payload → extraction → NeedCard (no Firestore)."""
    from app.services.intake_service import process_intake, IntakePayload
    from app.services.extraction_service import ExtractionResult, NeedType

    mock_extraction = ExtractionResult(
        need_type=NeedType.food,
        description_clean="40 families need food in Ward 12.",
        urgency_reasoning="2 days without food, children involved.",
        urgency_score=7.5,
        affected_count=40,
        skills_needed=["food_distribution"],
        location_text="Ward 12",
        contact_name="Ramesh",
        contact_detail="9887654321",
        source_channel=SourceChannel.text,
        raw_input="40 families need food",
        extraction_failed=False,
    )

    with (
        patch("app.services.intake_service.extract_need_fields",
              new_callable=AsyncMock, return_value=mock_extraction),
        patch("app.services.intake_service._check_exact_duplicate",
              new_callable=AsyncMock, return_value=None),
        patch("app.db.needcard_repo.create", new_callable=AsyncMock),
    ):
        result = await process_intake(IntakePayload(
            raw_text="40 families need food in Ward 12",
            source_channel=SourceChannel.text,
        ))

    assert result.is_duplicate is False
    assert result.need_type == "food"
    assert result.urgency_score == 7.5
    assert len(result.needcard_id) == 36  # UUID


@pytest.mark.asyncio
async def test_intake_service_dedup_returns_existing():
    from app.services.intake_service import process_intake, IntakePayload
    from app.services.extraction_service import ExtractionResult, NeedType

    mock_extraction = ExtractionResult(
        need_type=NeedType.food,
        description_clean="40 families need food.",
        urgency_reasoning="Duplicate report, same need.",
        urgency_score=7.5,
        source_channel=SourceChannel.text,
        raw_input="test",
        extraction_failed=False,
    )

    with (
        patch("app.services.intake_service.extract_need_fields",
              new_callable=AsyncMock, return_value=mock_extraction),
        patch("app.services.intake_service._check_exact_duplicate",
              new_callable=AsyncMock, return_value="nc-existing-001"),
        patch("app.services.intake_service._merge_into_existing",
              new_callable=AsyncMock),
    ):
        result = await process_intake(IntakePayload(
            raw_text="40 families need food.",
            source_channel=SourceChannel.text,
        ))

    assert result.is_duplicate is True
    assert result.needcard_id == "nc-existing-001"