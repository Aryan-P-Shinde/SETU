"""
Tests for extraction service and POST /api/v1/intake/text

All Gemini calls mocked. Tests cover:
- Happy path for all need types
- Validation: skill canonicalization, urgency clamping, null coercion
- Retry logic and failed-extraction fallback
- description_clean deduplication
- All three source channels
- Pydantic validation on bad LLM output
"""

import json
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.services.extraction_service import (
    ExtractionResult,
    NeedType,
    SourceChannel,
    _parse_and_validate,
    _failed_extraction,
    extract_need_fields,
)

GEMINI_CALL = "app.services.extraction_service._call_gemini"


# ── Helpers ───────────────────────────────────────────────────────────────────

def _gemini_json(**overrides) -> str:
    """Build a valid Gemini JSON response string."""
    base = {
        "need_type": "food",
        "description_clean": "40 families need food in Ward 12. No food for 2 days.",
        "urgency_reasoning": "Factors: 40 families affected, children involved, 2 days without food. No immediate life threat but serious. Score: 7.5",
        "urgency_score": 7.5,
        "affected_count": 40,
        "skills_needed": ["food_distribution"],
        "location_text": "Ward 12",
        "contact_name": "Ramesh",
        "contact_detail": "9876543210",
    }
    base.update(overrides)
    return json.dumps(base)


# ── Pydantic validation unit tests ────────────────────────────────────────────

def test_parse_valid_response():
    raw = _gemini_json()
    result = _parse_and_validate(raw, SourceChannel.text, "input text", "v1")
    assert result.need_type == NeedType.food
    assert result.urgency_score == 7.5
    assert result.affected_count == 40
    assert result.extraction_failed is False


def test_parse_strips_markdown_fences():
    raw = "```json\n" + _gemini_json() + "\n```"
    result = _parse_and_validate(raw, SourceChannel.voice, "input", "v1")
    assert result.need_type == NeedType.food


def test_parse_urgency_clamped_to_10():
    raw = _gemini_json(urgency_score=11.5)
    # Pydantic ge/le validation should reject > 10
    import pytest
    with pytest.raises(Exception):
        _parse_and_validate(raw, SourceChannel.text, "input", "v1")


def test_parse_unknown_skill_dropped():
    raw = _gemini_json(skills_needed=["food_distribution", "nonexistent_skill", "medical_doctor"])
    result = _parse_and_validate(raw, SourceChannel.text, "input", "v1")
    assert "nonexistent_skill" not in result.skills_needed
    assert "food_distribution" in result.skills_needed
    assert "medical_doctor" in result.skills_needed


def test_parse_empty_string_contact_becomes_none():
    raw = _gemini_json(contact_name="", contact_detail="null")
    result = _parse_and_validate(raw, SourceChannel.text, "input", "v1")
    assert result.contact_name is None
    assert result.contact_detail is None


def test_parse_affected_count_negative_becomes_none():
    raw = _gemini_json(affected_count=-5)
    result = _parse_and_validate(raw, SourceChannel.text, "input", "v1")
    assert result.affected_count is None


def test_failed_extraction_defaults():
    result = _failed_extraction("timeout", "raw input text", SourceChannel.image, "v1")
    assert result.extraction_failed is True
    assert result.urgency_score == 5.0
    assert result.need_type == NeedType.other
    assert result.raw_input == "raw input text"


def test_extraction_result_dict_for_needcard():
    raw = _gemini_json()
    result = _parse_and_validate(raw, SourceChannel.voice, "transcript", "v1")
    d = result.dict_for_needcard()
    assert "urgency_score_base" in d
    assert "location_text_raw" in d
    assert d["source_channel"] == "voice"


# ── Service-level tests with mocked Gemini ────────────────────────────────────

@pytest.mark.asyncio
async def test_extract_success():
    with patch(GEMINI_CALL, new_callable=AsyncMock, return_value=_gemini_json()):
        result = await extract_need_fields("40 families need food", SourceChannel.text)
    assert result.need_type == NeedType.food
    assert result.extraction_failed is False


@pytest.mark.asyncio
async def test_extract_retries_on_bad_json():
    """First call returns garbage JSON, second call succeeds."""
    responses = ["not json at all!!!", _gemini_json()]
    call_count = 0

    async def side_effect(*args, **kwargs):
        nonlocal call_count
        r = responses[call_count]
        call_count += 1
        return r

    with patch(GEMINI_CALL, side_effect=side_effect):
        result = await extract_need_fields("40 families need food", SourceChannel.text)

    assert call_count == 2
    assert result.extraction_failed is False


@pytest.mark.asyncio
async def test_extract_fails_both_retries_returns_fallback():
    """Both attempts fail → extraction_failed=True, not exception."""
    with patch(GEMINI_CALL, new_callable=AsyncMock, side_effect=Exception("timeout")):
        result = await extract_need_fields("some field report", SourceChannel.voice)

    assert result.extraction_failed is True
    assert result.urgency_score == 5.0
    assert result.raw_input == "some field report"


@pytest.mark.asyncio
async def test_extract_empty_input_returns_fallback():
    result = await extract_need_fields("   ", SourceChannel.text)
    assert result.extraction_failed is True


@pytest.mark.asyncio
async def test_extract_no_api_key_raises():
    import os
    original = os.environ.pop("GEMINI_API_KEY", None)
    try:
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY"):
            await extract_need_fields("help needed", SourceChannel.text)
    finally:
        if original:
            os.environ["GEMINI_API_KEY"] = original


# ── API endpoint tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_text_intake_endpoint_success():
    with patch(GEMINI_CALL, new_callable=AsyncMock, return_value=_gemini_json()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/intake/text", json={"text": "40 families need food in Ward 12"})

    assert resp.status_code == 200
    data = resp.json()
    assert data["need_type"] == "food"
    assert data["urgency_score"] == 7.5
    assert data["extraction_failed"] is False


@pytest.mark.asyncio
async def test_text_intake_endpoint_too_short():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        resp = await ac.post("/api/v1/intake/text", json={"text": "hi"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_text_intake_medical_rescue():
    raw = _gemini_json(
        need_type="rescue",
        urgency_score=9.8,
        affected_count=3,
        skills_needed=["search_rescue", "logistics_boat_operator"],
        description_clean="3 people trapped on rooftop at MG Road after flood.",
        contact_detail="9876543210",
    )
    with patch(GEMINI_CALL, new_callable=AsyncMock, return_value=raw):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/text",
                json={"text": "3 people trapped on roof 45 MG Road"},
            )

    assert resp.status_code == 200
    data = resp.json()
    assert data["need_type"] == "rescue"
    assert data["urgency_score"] == 9.8
    assert "search_rescue" in data["skills_needed"]


@pytest.mark.asyncio
async def test_text_intake_extraction_failed_still_200():
    """If extraction fails, endpoint returns 200 with extraction_failed=True (not 500)."""
    with patch(GEMINI_CALL, new_callable=AsyncMock, side_effect=Exception("network error")):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/text",
                json={"text": "Need help urgently at the flood zone"},
            )

    assert resp.status_code == 200
    assert resp.json()["extraction_failed"] is True


@pytest.mark.asyncio
async def test_text_intake_source_channel_tracked():
    with patch(GEMINI_CALL, new_callable=AsyncMock, return_value=_gemini_json()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/intake/text",
                json={"text": "40 families need food", "language_hint": "hi"},
            )
    assert resp.json()["source_channel"] == "text"
