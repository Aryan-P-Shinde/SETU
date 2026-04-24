"""
DispatchRecord — links a Volunteer to a NeedCard for one mission.

Firestore collection: dispatch_log
Document ID: DispatchRecord.id (UUID)
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class DispatchStatus(str, Enum):
    pending   = "pending"    # brief generated, not yet seen by volunteer
    accepted  = "accepted"   # volunteer accepted via app
    en_route  = "en_route"   # volunteer tapped "I'm on my way"
    completed = "completed"  # mission complete
    cancelled = "cancelled"  # NGO or volunteer cancelled


class DispatchRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))

    needcard_id: str
    volunteer_id: str

    # Match context (snapshot at dispatch time — don't re-query)
    match_score: float = Field(ge=0.0, le=1.0)
    distance_km: float = Field(ge=0.0)
    skill_overlap: list[str] = Field(default_factory=list)

    # Brief
    brief_text: str = ""
    brief_status: str = "draft"   # draft | approved | sent
    brief_edit_history: list[dict] = Field(default_factory=list)  # for fine-tuning signal

    # Lifecycle
    status: DispatchStatus = DispatchStatus.pending
    dispatched_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    accepted_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None

    def touch_accepted(self) -> None:
        self.status = DispatchStatus.accepted
        self.accepted_at = datetime.now(timezone.utc)

    def touch_completed(self) -> None:
        self.status = DispatchStatus.completed
        self.completed_at = datetime.now(timezone.utc)

    def touch_cancelled(self, reason: str = "") -> None:
        self.status = DispatchStatus.cancelled
        self.cancelled_at = datetime.now(timezone.utc)
        self.cancellation_reason = reason

    def to_firestore(self) -> dict:
        d = self.model_dump()
        for ts_field in ("dispatched_at", "accepted_at", "completed_at", "cancelled_at"):
            if isinstance(d.get(ts_field), datetime):
                d[ts_field] = d[ts_field].isoformat()
        return d

    @classmethod
    def from_firestore(cls, doc_id: str, data: dict) -> "DispatchRecord":
        data = dict(data)
        data["id"] = doc_id
        for ts_field in ("dispatched_at", "accepted_at", "completed_at", "cancelled_at"):
            if isinstance(data.get(ts_field), str):
                data[ts_field] = datetime.fromisoformat(data[ts_field])
        return cls(**data)