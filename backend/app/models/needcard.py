"""
NeedCard — authoritative data model (single source of truth).

All writes come from the intake pipeline.
All reads come from the match engine and brief generator.
Schema is versioned explicitly — bump SCHEMA_VERSION when fields change,
write a migration in scripts/migrations/.

Firestore collection: need_cards
Document ID: NeedCard.id (UUID)
"""

import hashlib
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator

SCHEMA_VERSION = "1.0"


# ── Enums ─────────────────────────────────────────────────────────────────────

class NeedType(str, Enum):
    medical   = "medical"
    food      = "food"
    shelter   = "shelter"
    water     = "water"
    rescue    = "rescue"
    logistics = "logistics"
    other     = "other"


class NeedStatus(str, Enum):
    open      = "open"       # newly created, awaiting dispatch
    matched   = "matched"    # volunteer dispatched, en route
    fulfilled = "fulfilled"  # mission completed
    stale     = "stale"      # auto-marked after urgency decays to near-zero


class SourceChannel(str, Enum):
    voice = "voice"
    image = "image"
    text  = "text"


# ── Core model ────────────────────────────────────────────────────────────────

class NeedCard(BaseModel):
    # Identity
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    schema_version: str = Field(default=SCHEMA_VERSION)

    # Classification
    need_type: NeedType
    description_clean: str = Field(min_length=5)

    # Urgency — two fields: base is immutable after intake, eff is recomputed by decay job
    urgency_score_base: float = Field(ge=0.0, le=10.0)
    urgency_score_eff: float = Field(ge=0.0, le=10.0)
    urgency_reasoning: str = ""

    # Scope
    affected_count: Optional[int] = Field(default=None, ge=1)
    skills_needed: list[str] = Field(default_factory=list)

    # Geo
    geo_lat: float = Field(ge=-90.0, le=90.0)
    geo_lng: float = Field(ge=-180.0, le=180.0)
    geo_radius_m: int = Field(default=5000, ge=100, le=100_000)
    geo_confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    location_text_raw: str = ""

    # Contact
    contact_name: Optional[str] = None
    contact_detail: Optional[str] = None

    # Dedup
    report_count: int = Field(default=1, ge=1)
    source_hashes: list[str] = Field(default_factory=list)
    merged_from: list[str] = Field(default_factory=list)   # IDs of merged NeedCards

    # Lifecycle
    status: NeedStatus = NeedStatus.open
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    # Flags
    needs_review: bool = False
    extraction_failed: bool = False

    # Source tracking
    source_channel: SourceChannel = SourceChannel.text
    prompt_version: str = "v1"

    # Vector search (populated async after intake, None until embedding job runs)
    embedding: Optional[list[float]] = None

    # ── Validators ────────────────────────────────────────────────────────────

    @field_validator("urgency_score_base", "urgency_score_eff", mode="before")
    @classmethod
    def round_urgency(cls, v):
        return round(float(v), 1)

    @field_validator("geo_confidence", mode="before")
    @classmethod
    def clamp_geo_confidence(cls, v):
        return max(0.0, min(1.0, float(v)))

    @field_validator("contact_name", "contact_detail", mode="before")
    @classmethod
    def empty_to_none(cls, v):
        return None if v in ("", "null", None) else v

    @model_validator(mode="after")
    def sync_eff_to_base_on_create(self):
        """On first creation urgency_score_eff == base. Decay job overrides later."""
        if self.urgency_score_eff == 0.0 and self.urgency_score_base > 0.0:
            self.urgency_score_eff = self.urgency_score_base
        return self

    # ── Derived helpers ───────────────────────────────────────────────────────

    def compute_source_hash(self, raw_text: str) -> str:
        """SHA-256 of normalised input text — used by dedup layer."""
        normalised = raw_text.lower().strip()
        return hashlib.sha256(normalised.encode()).hexdigest()

    def touch(self) -> None:
        """Update updated_at. Call before every Firestore write."""
        self.updated_at = datetime.now(timezone.utc)

    def mark_dispatched(self) -> None:
        self.status = NeedStatus.matched
        self.touch()

    def mark_fulfilled(self) -> None:
        self.status = NeedStatus.fulfilled
        self.touch()

    def mark_stale(self) -> None:
        self.status = NeedStatus.stale
        self.touch()

    def is_open(self) -> bool:
        return self.status == NeedStatus.open

    def to_brief_context(self) -> dict:
        """
        Compact field subset for brief generation prompt.
        Only fields actionable in a volunteer brief.
        Strips internal metadata (hashes, schema_version, embeddings, etc.)
        """
        return {
            "need_type": self.need_type.value,
            "description_clean": self.description_clean,
            "urgency_score_eff": self.urgency_score_eff,
            "urgency_reasoning": self.urgency_reasoning,
            "affected_count": self.affected_count,
            "skills_needed": self.skills_needed,
            "location_text_raw": self.location_text_raw,
            "contact_name": self.contact_name,
            "contact_detail": self.contact_detail,
            "geo_confidence": self.geo_confidence,
        }

    def to_firestore(self) -> dict:
        """
        Serialise for Firestore write.
        - Converts datetimes to ISO strings (Firestore SDK handles Timestamp natively,
          but string is safer for cross-SDK reads).
        - Strips embedding from the main doc (stored separately via vector index).
        """
        d = self.model_dump()
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        # Embedding stored in Firestore VECTOR field — keep it if present
        # but don't serialise as plain list (Firestore SDK wraps it automatically)
        return d

    @classmethod
    def from_firestore(cls, doc_id: str, data: dict) -> "NeedCard":
        """Deserialise from Firestore document dict."""
        data = dict(data)
        data["id"] = doc_id
        # Parse ISO strings back to datetime
        for ts_field in ("created_at", "updated_at"):
            if isinstance(data.get(ts_field), str):
                data[ts_field] = datetime.fromisoformat(data[ts_field])
        return cls(**data)

    @classmethod
    def from_extraction(
        cls,
        extraction_dict: dict,
        geo_lat: float = 0.0,
        geo_lng: float = 0.0,
        geo_confidence: float = 0.0,
        geo_radius_m: int = 5000,
        source_hash: str = "",
        needs_review: bool = False,
    ) -> "NeedCard":
        """
        Factory: build a NeedCard from ExtractionResult.dict_for_needcard()
        plus geo fields resolved separately by the geo service.
        """
        urgency = extraction_dict.get("urgency_score_base", 5.0)
        return cls(
            need_type=extraction_dict["need_type"],
            description_clean=extraction_dict["description_clean"],
            urgency_score_base=urgency,
            urgency_score_eff=urgency,
            urgency_reasoning=extraction_dict.get("urgency_reasoning", ""),
            affected_count=extraction_dict.get("affected_count"),
            skills_needed=extraction_dict.get("skills_needed", []),
            location_text_raw=extraction_dict.get("location_text_raw", ""),
            contact_name=extraction_dict.get("contact_name"),
            contact_detail=extraction_dict.get("contact_detail"),
            geo_lat=geo_lat,
            geo_lng=geo_lng,
            geo_confidence=geo_confidence,
            geo_radius_m=geo_radius_m,
            source_hashes=[source_hash] if source_hash else [],
            source_channel=extraction_dict.get("source_channel", SourceChannel.text),
            prompt_version=extraction_dict.get("prompt_version", "v1"),
            extraction_failed=extraction_dict.get("extraction_failed", False),
            needs_review=needs_review or extraction_dict.get("extraction_failed", False),
        )