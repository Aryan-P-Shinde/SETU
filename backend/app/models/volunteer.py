"""
Volunteer — data model.

Firestore collection: volunteers
Document ID: Volunteer.id (Firebase UID from phone auth)
"""

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from app.services.extraction_service import CANONICAL_SKILLS   # shared skill taxonomy


class AvailabilityStatus(str, Enum):
    available = "available"
    busy      = "busy"
    offline   = "offline"


class Volunteer(BaseModel):
    # Identity (Firebase UID — set by auth, not generated here)
    id: str

    # Profile
    name: str = Field(min_length=1)
    phone: str = ""                  # masked in match API until NGO confirms dispatch
    language_pref: str = "en"        # ISO 639-1 — brief will be generated in this lang

    # Skills — validated against canonical taxonomy
    skills: list[str] = Field(default_factory=list)

    # Location (updated by volunteer app on each session start)
    current_lat: float = Field(ge=-90.0, le=90.0)
    current_lng: float = Field(ge=-180.0, le=180.0)
    last_location_update: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    # Availability
    availability: AvailabilityStatus = AvailabilityStatus.offline
    max_radius_km: int = Field(default=10, ge=1, le=200)

    # Stats (for leaderboard and volunteer app)
    total_hours: float = Field(default=0.0, ge=0.0)
    completed_missions: int = Field(default=0, ge=0)
    current_dispatch_id: Optional[str] = None   # set when availability=busy

    # FCM push token — registered by volunteer app on first launch, refreshed on login
    # Used by delivery_service to send mission brief push notification
    # None = volunteer hasn't opened the app yet; brief still visible on next open
    fcm_token: Optional[str] = None

    # Geohash fields — populated by service before Firestore write
    # Used by match engine for bounding-box geo queries
    geohash_4: str = ""   # 4-char geohash  (~40km precision)
    geohash_5: str = ""   # 5-char geohash  (~5km precision)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("skills", mode="before")
    @classmethod
    def validate_skills(cls, v):
        if not isinstance(v, list):
            return []
        return [s for s in v if s in CANONICAL_SKILLS]

    # ── Helpers ───────────────────────────────────────────────────────────────

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def set_busy(self, dispatch_id: str) -> None:
        self.availability = AvailabilityStatus.busy
        self.current_dispatch_id = dispatch_id
        self.touch()

    def set_available(self) -> None:
        self.availability = AvailabilityStatus.available
        self.current_dispatch_id = None
        self.touch()

    def masked_phone(self) -> str:
        """Return last 4 digits only — shown in match list before NGO confirms."""
        if len(self.phone) >= 4:
            return f"****{self.phone[-4:]}"
        return "****"

    def to_firestore(self) -> dict:
        d = self.model_dump()
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        d["last_location_update"] = self.last_location_update.isoformat()
        return d

    @classmethod
    def from_firestore(cls, doc_id: str, data: dict) -> "Volunteer":
        data = dict(data)
        data["id"] = doc_id
        for ts_field in ("created_at", "updated_at", "last_location_update"):
            if isinstance(data.get(ts_field), str):
                data[ts_field] = datetime.fromisoformat(data[ts_field])
        return cls(**data)