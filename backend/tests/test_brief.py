"""
Tests for brief router — all DB and Gemini calls mocked.
Covers: generate, get, edit, approve, send (FCM), delivery failures.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app
from app.models.dispatch import DispatchRecord
from app.models.needcard import NeedCard, NeedType
from app.models.volunteer import Volunteer, AvailabilityStatus
from app.services.delivery_service import DeliveryChannel, DeliveryResult

GEMINI = "app.services.brief_service._call_gemini"

SAMPLE_BRIEF = (
    "HIGH urgency — 40 families in Ward 12 have had no food for 2 days. "
    "Go to Ward 12, near the government school. Bring dry rations and water. "
    "Contact Ramesh Kumar on arrival: 9887654321. Estimated time 2-3 hours."
)


# ── Fixtures ──────────────────────────────────────────────────────────────────

def _dispatch(brief_text="", brief_status="draft") -> DispatchRecord:
    r = DispatchRecord(
        needcard_id="nc_001", volunteer_id="vol_001",
        match_score=0.87, distance_km=2.3,
    )
    r.brief_text = brief_text
    r.brief_status = brief_status
    return r


def _card(geo_confidence=0.9) -> NeedCard:
    return NeedCard(
        need_type=NeedType.food,
        description_clean="40 families need food in Ward 12.",
        urgency_score_base=7.5, urgency_score_eff=7.5,
        geo_lat=22.572, geo_lng=88.363,
        geo_confidence=geo_confidence,
        location_text_raw="Ward 12",
        contact_name="Ramesh Kumar", contact_detail="9887654321",
    )


def _volunteer(fcm_token=None) -> Volunteer:
    v = Volunteer(id="vol_001", name="Arjun Mehta", skills=["food_distribution"],
                  current_lat=22.5, current_lng=88.3)
    v.language_pref = "en"
    v.fcm_token = fcm_token
    return v


def _ctx(brief_text="", brief_status="draft", fcm_token=None, geo_confidence=0.9):
    """Returns list of patches + the dispatch object."""
    d = _dispatch(brief_text, brief_status)
    return [
        patch("app.routers.brief.dispatch_repo.get", new_callable=AsyncMock, return_value=d),
        patch("app.routers.brief.needcard_repo.get", new_callable=AsyncMock, return_value=_card(geo_confidence)),
        patch("app.routers.brief.volunteer_repo.get", new_callable=AsyncMock, return_value=_volunteer(fcm_token)),
        patch("app.routers.brief.dispatch_repo.update", new_callable=AsyncMock),
    ], d


# ── Generate ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_brief_success():
    patches, _ = _ctx()
    with patches[0], patches[1], patches[2], patches[3], \
         patch(GEMINI, new_callable=AsyncMock, return_value=SAMPLE_BRIEF):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/brief/d-001")

    assert resp.status_code == 201
    data = resp.json()
    assert data["brief_text"] == SAMPLE_BRIEF
    assert data["brief_status"] == "draft"
    assert data["generation_failed"] is False
    assert data["map_link"] == "https://maps.google.com/?q=22.572,88.363&zoom=17"
    assert "created_at" in data
    assert data["word_count"] > 0


@pytest.mark.asyncio
async def test_create_brief_no_map_link_low_confidence():
    patches, _ = _ctx(geo_confidence=0.1)
    with patches[0], patches[1], patches[2], patches[3], \
         patch(GEMINI, new_callable=AsyncMock, return_value=SAMPLE_BRIEF):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/brief/d-001")
    assert resp.json()["map_link"] is None


@pytest.mark.asyncio
async def test_create_brief_dispatch_not_found():
    with patch("app.routers.brief.dispatch_repo.get", new_callable=AsyncMock, return_value=None):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/brief/nonexistent")
    assert resp.status_code == 404


# ── Get ───────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_brief_success():
    dispatch = _dispatch(brief_text=SAMPLE_BRIEF, brief_status="approved")
    with (
        patch("app.routers.brief.dispatch_repo.get", new_callable=AsyncMock, return_value=dispatch),
        patch("app.routers.brief.needcard_repo.get", new_callable=AsyncMock, return_value=_card()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/brief/d-001")
    assert resp.status_code == 200
    assert resp.json()["brief_status"] == "approved"


@pytest.mark.asyncio
async def test_get_brief_not_generated():
    dispatch = _dispatch(brief_text="")
    with patch("app.routers.brief.dispatch_repo.get", new_callable=AsyncMock, return_value=dispatch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.get("/api/v1/brief/d-001")
    assert resp.status_code == 404


# ── Edit ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_edit_brief_resets_to_draft():
    patches, _ = _ctx(brief_text=SAMPLE_BRIEF, brief_status="approved")
    edited = "Updated: Go to Ward 12 now. 40 families need food. Bring rations. Call Ramesh 9887654321."
    with patches[0], patches[1], patches[2], patches[3]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch("/api/v1/brief/d-001", json={"edited_text": edited})
    assert resp.status_code == 200
    assert resp.json()["brief_status"] == "draft"
    assert resp.json()["brief_text"] == edited


@pytest.mark.asyncio
async def test_edit_brief_blocked_when_sent():
    dispatch = _dispatch(brief_text=SAMPLE_BRIEF, brief_status="sent")
    with patch("app.routers.brief.dispatch_repo.get", new_callable=AsyncMock, return_value=dispatch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.patch("/api/v1/brief/d-001",
                                  json={"edited_text": "Trying to edit a sent brief here."})
    assert resp.status_code == 400


# ── Approve ───────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_approve_brief():
    patches, _ = _ctx(brief_text=SAMPLE_BRIEF, brief_status="draft")
    with patches[0], patches[1], patches[2], patches[3]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/brief/d-001/approve")
    assert resp.status_code == 200
    assert resp.json()["brief_status"] == "approved"


@pytest.mark.asyncio
async def test_approve_failed_brief_blocked():
    dispatch = _dispatch(
        brief_text="[Brief generation failed — please write this brief manually]",
        brief_status="draft",
    )
    with patch("app.routers.brief.dispatch_repo.get", new_callable=AsyncMock, return_value=dispatch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/brief/d-001/approve")
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_approve_already_sent_blocked():
    dispatch = _dispatch(brief_text=SAMPLE_BRIEF, brief_status="sent")
    with patch("app.routers.brief.dispatch_repo.get", new_callable=AsyncMock, return_value=dispatch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/brief/d-001/approve")
    assert resp.status_code == 400


# ── Send ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_send_brief_fcm_success():
    patches, _ = _ctx(brief_text=SAMPLE_BRIEF, brief_status="approved", fcm_token="tok-xyz")
    ok = DeliveryResult(success=True, channel=DeliveryChannel.fcm, message_id="msg-001")
    with patches[0], patches[1], patches[2], patches[3], \
         patch("app.routers.brief.deliver_brief", new_callable=AsyncMock, return_value=ok):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/brief/d-001/send")

    assert resp.status_code == 200
    data = resp.json()
    assert data["brief_status"] == "sent"
    assert data["delivery_success"] is True
    assert data["delivery_channel"] == "fcm"
    assert data["delivery_error"] is None
    assert data["map_link"] == "https://maps.google.com/?q=22.572,88.363&zoom=17"
    assert "created_at" in data


@pytest.mark.asyncio
async def test_send_brief_no_token_still_marks_sent():
    """No FCM token → push fails but brief is still marked sent."""
    patches, _ = _ctx(brief_text=SAMPLE_BRIEF, brief_status="approved", fcm_token=None)
    fail = DeliveryResult(
        success=False, channel=DeliveryChannel.fcm,
        error="No FCM token registered for this volunteer",
    )
    with patches[0], patches[1], patches[2], patches[3], \
         patch("app.routers.brief.deliver_brief", new_callable=AsyncMock, return_value=fail):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/brief/d-001/send")

    data = resp.json()
    assert data["brief_status"] == "sent"       # still marked sent
    assert data["delivery_success"] is False
    assert "No FCM token" in data["delivery_error"]


@pytest.mark.asyncio
async def test_send_requires_approved_status():
    patches, _ = _ctx(brief_text=SAMPLE_BRIEF, brief_status="draft")
    with patches[0], patches[1], patches[2], patches[3]:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            resp = await ac.post("/api/v1/brief/d-001/send")
    assert resp.status_code == 400
    assert "approved" in resp.json()["detail"]


# ── Delivery service unit ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delivery_no_token_returns_failure():
    from app.services.delivery_service import deliver_brief
    result = await deliver_brief(
        brief_text=SAMPLE_BRIEF, map_link=None,
        volunteer_id="v1", dispatch_id="d1", fcm_token=None,
    )
    assert result.success is False
    assert "No FCM token" in result.error


@pytest.mark.asyncio
async def test_delivery_fcm_http_error_returns_failure(monkeypatch):
    from app.services.delivery_service import deliver_brief
    import httpx

    monkeypatch.setenv("FIREBASE_PROJECT_ID", "test-project")

    with patch("app.services.delivery_service._get_fcm_access_token",
               new_callable=AsyncMock, return_value="tok"):
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = "Unauthorized"
        mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "401", request=MagicMock(), response=mock_resp
        )
        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value = mock_client

            result = await deliver_brief(
                brief_text=SAMPLE_BRIEF, map_link=None,
                volunteer_id="v1", dispatch_id="d1", fcm_token="some-token",
            )

    assert result.success is False
    assert "401" in result.error