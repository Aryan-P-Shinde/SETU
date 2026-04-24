"""
Tests for NeedCard, Volunteer, DispatchRecord models.
No Firestore — pure Pydantic validation tests.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.models.needcard import NeedCard, NeedType, NeedStatus, SourceChannel, SCHEMA_VERSION
from app.models.volunteer import Volunteer, AvailabilityStatus
from app.models.dispatch import DispatchRecord, DispatchStatus


# ── NeedCard ──────────────────────────────────────────────────────────────────

def _make_card(**overrides) -> NeedCard:
    defaults = dict(
        need_type="rescue",
        description_clean="3 people trapped on rooftop after flood.",
        urgency_score_base=9.5,
        urgency_score_eff=9.5,
        geo_lat=22.5726,
        geo_lng=88.3639,
    )
    defaults.update(overrides)
    return NeedCard(**defaults)


def test_needcard_defaults():
    card = _make_card()
    assert card.schema_version == SCHEMA_VERSION
    assert card.status == NeedStatus.open
    assert card.report_count == 1
    assert card.needs_review is False
    assert card.embedding is None
    assert len(card.id) == 36  # UUID


def test_needcard_urgency_rounded():
    card = _make_card(urgency_score_base=7.567, urgency_score_eff=7.567)
    assert card.urgency_score_base == 7.6
    assert card.urgency_score_eff == 7.6


def test_needcard_urgency_clamped():
    with pytest.raises(ValidationError):
        _make_card(urgency_score_base=11.0, urgency_score_eff=11.0)


def test_needcard_empty_contact_becomes_none():
    card = _make_card(contact_name="", contact_detail="null")
    assert card.contact_name is None
    assert card.contact_detail is None


def test_needcard_negative_affected_count_rejected():
    with pytest.raises(ValidationError):
        _make_card(affected_count=-1)


def test_needcard_geo_bounds_validated():
    with pytest.raises(ValidationError):
        _make_card(geo_lat=91.0)
    with pytest.raises(ValidationError):
        _make_card(geo_lng=181.0)


def test_needcard_eff_syncs_to_base_on_create():
    """If urgency_score_eff is 0 and base > 0, eff should be set to base."""
    card = _make_card(urgency_score_base=8.0, urgency_score_eff=0.0)
    assert card.urgency_score_eff == 8.0


def test_needcard_status_transitions():
    card = _make_card()
    assert card.is_open()
    card.mark_dispatched()
    assert card.status == NeedStatus.matched
    assert not card.is_open()
    card.mark_fulfilled()
    assert card.status == NeedStatus.fulfilled


def test_needcard_source_hash():
    card = _make_card()
    h1 = card.compute_source_hash("help needed at ward 12 ")
    h2 = card.compute_source_hash("HELP NEEDED AT WARD 12")
    assert h1 == h2  # normalised


def test_needcard_to_firestore_iso_dates():
    card = _make_card()
    d = card.to_firestore()
    assert isinstance(d["created_at"], str)
    assert "T" in d["created_at"]  # ISO format


def test_needcard_from_firestore_roundtrip():
    card = _make_card()
    d = card.to_firestore()
    restored = NeedCard.from_firestore(card.id, d)
    assert restored.id == card.id
    assert restored.need_type == card.need_type
    assert restored.urgency_score_base == card.urgency_score_base


def test_needcard_from_extraction():
    extraction = {
        "need_type": "food",
        "description_clean": "40 families need food in Ward 12.",
        "urgency_score_base": 7.5,
        "urgency_reasoning": "2 days without food, 40 families, children involved.",
        "affected_count": 40,
        "skills_needed": ["food_distribution"],
        "location_text_raw": "Ward 12, Shyamnagar",
        "contact_name": "Ramesh",
        "contact_detail": "9876543210",
        "source_channel": "voice",
        "prompt_version": "v1",
        "extraction_failed": False,
    }
    card = NeedCard.from_extraction(
        extraction,
        geo_lat=22.59, geo_lng=88.32, geo_confidence=0.85,
        source_hash="abc123",
    )
    assert card.need_type == NeedType.food
    assert card.geo_lat == 22.59
    assert "abc123" in card.source_hashes
    assert card.source_channel == SourceChannel.voice


def test_needcard_from_extraction_failed_sets_review():
    extraction = {
        "need_type": "other",
        "description_clean": "[Extraction failed]",
        "urgency_score_base": 5.0,
        "urgency_reasoning": "Failed",
        "skills_needed": [],
        "location_text_raw": "",
        "extraction_failed": True,
        "source_channel": "text",
        "prompt_version": "v1",
    }
    card = NeedCard.from_extraction(extraction)
    assert card.needs_review is True
    assert card.extraction_failed is True


# ── Volunteer ─────────────────────────────────────────────────────────────────

def _make_volunteer(**overrides) -> Volunteer:
    defaults = dict(
        id="vol_001",
        name="Arjun Sharma",
        skills=["medical_first_aid", "logistics_driver"],
        current_lat=22.5726,
        current_lng=88.3639,
    )
    defaults.update(overrides)
    return Volunteer(**defaults)


def test_volunteer_defaults():
    vol = _make_volunteer()
    assert vol.availability == AvailabilityStatus.offline
    assert vol.max_radius_km == 10
    assert vol.total_hours == 0.0


def test_volunteer_invalid_skill_dropped():
    vol = _make_volunteer(skills=["medical_first_aid", "flying_a_helicopter", "food_distribution"])
    assert "flying_a_helicopter" not in vol.skills
    assert "medical_first_aid" in vol.skills
    assert "food_distribution" in vol.skills


def test_volunteer_geo_bounds():
    with pytest.raises(ValidationError):
        _make_volunteer(current_lat=95.0)


def test_volunteer_set_busy():
    vol = _make_volunteer()
    vol.set_busy("dispatch_123")
    assert vol.availability == AvailabilityStatus.busy
    assert vol.current_dispatch_id == "dispatch_123"


def test_volunteer_set_available():
    vol = _make_volunteer()
    vol.set_busy("dispatch_123")
    vol.set_available()
    assert vol.availability == AvailabilityStatus.available
    assert vol.current_dispatch_id is None


def test_volunteer_masked_phone():
    vol = _make_volunteer(phone="9876543210")
    assert vol.masked_phone() == "****3210"


def test_volunteer_firestore_roundtrip():
    vol = _make_volunteer()
    d = vol.to_firestore()
    restored = Volunteer.from_firestore(vol.id, d)
    assert restored.name == vol.name
    assert restored.skills == vol.skills


# ── DispatchRecord ────────────────────────────────────────────────────────────

def _make_dispatch(**overrides) -> DispatchRecord:
    defaults = dict(
        needcard_id="nc_001",
        volunteer_id="vol_001",
        match_score=0.87,
        distance_km=2.3,
        skill_overlap=["medical_first_aid"],
    )
    defaults.update(overrides)
    return DispatchRecord(**defaults)


def test_dispatch_defaults():
    d = _make_dispatch()
    assert d.status == DispatchStatus.pending
    assert d.brief_status == "draft"
    assert d.accepted_at is None


def test_dispatch_lifecycle():
    d = _make_dispatch()
    d.touch_accepted()
    assert d.status == DispatchStatus.accepted
    assert d.accepted_at is not None
    d.touch_completed()
    assert d.status == DispatchStatus.completed
    assert d.completed_at is not None


def test_dispatch_cancel():
    d = _make_dispatch()
    d.touch_cancelled("Volunteer unreachable")
    assert d.status == DispatchStatus.cancelled
    assert d.cancellation_reason == "Volunteer unreachable"


def test_dispatch_match_score_clamped():
    with pytest.raises(ValidationError):
        _make_dispatch(match_score=1.5)


def test_dispatch_firestore_roundtrip():
    d = _make_dispatch()
    d.touch_accepted()
    data = d.to_firestore()
    restored = DispatchRecord.from_firestore(d.id, data)
    assert restored.status == DispatchStatus.accepted
    assert restored.accepted_at is not None