"""
Tests for POST /api/v1/intake/image

All Gemini calls mocked — CI has no API key.
Covers: happy path, blurry/low-confidence, unreadable, timeouts, retry logic,
        file validation, handwritten forms, WhatsApp screenshots.
"""

import io
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.gemini_ocr_service import OCRResult

# ── Helpers ───────────────────────────────────────────────────────────────────
def _fake_img(content: bytes = b"PNG\x89fake", filename: str = "form.png"):
    return {"file": (filename, io.BytesIO(content), "image/png")}


def _make_result(**kwargs) -> OCRResult:
    defaults = dict(
        extracted_text="25 families need food and water. Contact: Ramesh 9876543210",
        confidence=0.92,
        needs_review=False,
        language="en",
        image_quality="clear",
        text_regions=[
            {"label": "printed_text", "content": "25 families need food", "legible": True}
        ],
        illegible_count=0,
        confidence_indicators={
            "is_blurry": False,
            "is_low_light": False,
            "is_handwritten": False,
            "is_printed": True,
            "partial_occlusion": False,
        },
        raw_response='{"extracted_text": "..."}',
    )
    defaults.update(kwargs)
    return OCRResult(**defaults)


SERVICE = "app.routers.image_intake.extract_text_from_image"


# ── Happy path ────────────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_image_intake_clear_printed():
    with patch(SERVICE, new_callable=AsyncMock, return_value=_make_result()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/intake/image", files=_fake_img())

    assert resp.status_code == 200
    data = resp.json()
    assert data["confidence"] == 0.92
    assert data["needs_review"] is False
    assert "families" in data["extracted_text"]
    assert data["image_quality"] == "clear"


@pytest.mark.asyncio
async def test_image_intake_hindi_handwritten():
    result = _make_result(
        extracted_text="पंद्रह लोगों को दवाई चाहिए [illegible] वार्ड 7",
        confidence=0.71,
        needs_review=False,
        language="hi",
        image_quality="moderate",
        illegible_count=1,
        confidence_indicators={
            "is_blurry": False, "is_low_light": False,
            "is_handwritten": True, "is_printed": False, "partial_occlusion": False,
        },
    )
    with patch(SERVICE, new_callable=AsyncMock, return_value=result):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/intake/image", files=_fake_img(filename="survey.jpg"))

    assert resp.status_code == 200
    data = resp.json()
    assert data["language_detected"] == "hi"
    assert data["illegible_regions_count"] == 1


# ── needs_review triggers ─────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_image_intake_blurry_whatsapp_screenshot():
    """Blurry WhatsApp screenshot → needs_review=True, low confidence."""
    result = _make_result(
        extracted_text="[illegible] [illegible] help [illegible]",
        confidence=0.28,
        needs_review=True,
        image_quality="poor",
        illegible_count=3,
        confidence_indicators={
            "is_blurry": True, "is_low_light": False,
            "is_handwritten": False, "is_printed": False, "partial_occlusion": False,
        },
    )
    with patch(SERVICE, new_callable=AsyncMock, return_value=result):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/intake/image", files=_fake_img())

    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_review"] is True
    assert data["confidence"] < 0.6


@pytest.mark.asyncio
async def test_image_intake_completely_unreadable():
    result = _make_result(
        extracted_text="",
        confidence=0.0,
        needs_review=True,
        image_quality="unreadable",
        illegible_count=0,
    )
    with patch(SERVICE, new_callable=AsyncMock, return_value=result):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/intake/image", files=_fake_img())

    assert resp.status_code == 200
    data = resp.json()
    assert data["needs_review"] is True
    assert data["extracted_text"] == ""
    assert data["confidence"] == 0.0


# ── Retry / timeout fallback ──────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_image_intake_timeout_returns_review_flag():
    """After retries, service returns needs_review=True fallback (not 500)."""
    fallback = _make_result(
        extracted_text="",
        confidence=0.0,
        needs_review=True,
        image_quality="unknown",
    )
    with patch(SERVICE, new_callable=AsyncMock, return_value=fallback):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/intake/image", files=_fake_img())

    assert resp.status_code == 200
    assert resp.json()["needs_review"] is True


@pytest.mark.asyncio
async def test_image_intake_service_unavailable():
    """RuntimeError (no API key) → 503."""
    with patch(SERVICE, new_callable=AsyncMock, side_effect=RuntimeError("GEMINI_API_KEY not set")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/intake/image", files=_fake_img())

    assert resp.status_code == 503


# ── File validation ───────────────────────────────────────────────────────────
@pytest.mark.asyncio
async def test_image_intake_empty_file():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/intake/image", files=_fake_img(content=b""))
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_image_intake_too_large():
    big = b"x" * (21 * 1024 * 1024)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/intake/image", files=_fake_img(content=big))
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_image_intake_wrong_type():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post(
            "/api/v1/intake/image",
            files={"file": ("doc.pdf", io.BytesIO(b"pdf"), "application/pdf")},
        )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_image_intake_jpeg_extension():
    """Extension-based MIME resolution: .jpg → image/jpeg."""
    with patch(SERVICE, new_callable=AsyncMock, return_value=_make_result()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/image",
                files={"file": ("photo.jpg", io.BytesIO(b"fake-jpeg"), "application/octet-stream")},
            )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_image_intake_webp():
    with patch(SERVICE, new_callable=AsyncMock, return_value=_make_result()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/image",
                files={"file": ("screenshot.webp", io.BytesIO(b"webp-data"), "image/webp")},
            )
    assert resp.status_code == 200


# ── Confidence scoring unit tests ─────────────────────────────────────────────
def test_confidence_scoring_clear_image():
    from app.services.gemini_ocr_service import _derive_confidence
    score = _derive_confidence(
        extracted_text="50 families need water",
        image_quality="clear",
        illegible_count=0,
        text_regions=[{"label": "printed_text", "content": "50 families", "legible": True}],
        confidence_indicators={
            "is_blurry": False, "is_low_light": False,
            "is_handwritten": False, "is_printed": True, "partial_occlusion": False,
        },
    )
    assert score >= 0.9


def test_confidence_scoring_blurry_handwritten():
    from app.services.gemini_ocr_service import _derive_confidence
    score = _derive_confidence(
        extracted_text="[illegible] [illegible] help needed [illegible]",
        image_quality="poor",
        illegible_count=3,
        text_regions=[],
        confidence_indicators={
            "is_blurry": True, "is_low_light": True,
            "is_handwritten": True, "is_printed": False, "partial_occlusion": False,
        },
    )
    assert score < 0.6  # must trigger needs_review


def test_confidence_scoring_empty_text():
    from app.services.gemini_ocr_service import _derive_confidence
    score = _derive_confidence(
        extracted_text="",
        image_quality="unreadable",
        illegible_count=0,
        text_regions=[],
        confidence_indicators={},
    )
    assert score == 0.0