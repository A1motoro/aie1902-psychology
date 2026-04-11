from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

GAD7_ITEM_IDS = tuple(f"Q{i}" for i in range(1, 8))


class SessionState(str, Enum):
    collecting = "collecting"
    completed = "completed"
    archived = "archived"


class Preferences(BaseModel):
    tone: str = "supportive"
    disclaimer_acknowledged: bool = False


class SessionMeta(BaseModel):
    session_id: str
    created_at: datetime
    state: SessionState
    model_id: str
    locale: str = "zh-CN"
    user_pseudo_id: Optional[str] = None
    preferences: Preferences = Field(default_factory=Preferences)
    closed_at: Optional[datetime] = None


class GAD7Progress(BaseModel):
    answered_items: list[str]
    pending_items: list[str]


class MessageRow(BaseModel):
    id: str
    role: str
    content: str
    created_at: datetime
    client_message_id: Optional[str] = None


class GAD7ItemSnapshot(BaseModel):
    score: Optional[int] = None
    confidence: float = 0.0
    needs_clarification: bool = False


class GAD7Snapshot(BaseModel):
    items: dict[str, GAD7ItemSnapshot]
    total: Optional[int] = None
    severity_band: Optional[str] = None
    ready_for_summary: bool = False


class ItemInternal(BaseModel):
    """打分引擎内部状态（含锁定，不直接暴露给 API）"""

    score: Optional[int] = None
    confidence: float = 0.0
    needs_clarification: bool = False
    locked: bool = False


class SessionInternal(BaseModel):
    meta: SessionMeta
    messages: list[MessageRow] = Field(default_factory=list)
    item_states: dict[str, ItemInternal] = Field(default_factory=dict)
    snapshot_version: int = 0

    @model_validator(mode="after")
    def ensure_item_states(self) -> SessionInternal:
        if not self.item_states:
            self.item_states = {q: ItemInternal() for q in GAD7_ITEM_IDS}
        else:
            for q in GAD7_ITEM_IDS:
                if q not in self.item_states:
                    self.item_states[q] = ItemInternal()
        return self


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def severity_from_total(total: int) -> str:
    if total <= 4:
        return "minimal"
    if total <= 9:
        return "mild"
    if total <= 14:
        return "moderate"
    return "severe"


def gad7_progress_from_states(item_states: dict[str, ItemInternal]) -> GAD7Progress:
    answered = [q for q in GAD7_ITEM_IDS if item_states[q].locked and item_states[q].score is not None]
    pending = [q for q in GAD7_ITEM_IDS if q not in answered]
    return GAD7Progress(answered_items=answered, pending_items=pending)


def to_public_snapshot(item_states: dict[str, ItemInternal]) -> GAD7Snapshot:
    items = {
        q: GAD7ItemSnapshot(
            score=s.score,
            confidence=s.confidence,
            needs_clarification=s.needs_clarification,
        )
        for q, s in item_states.items()
    }
    all_locked = all(item_states[q].locked and item_states[q].score is not None for q in GAD7_ITEM_IDS)
    total: Optional[int] = None
    severity: Optional[str] = None
    if all_locked:
        total = sum(item_states[q].score or 0 for q in GAD7_ITEM_IDS)
        severity = severity_from_total(total)
    return GAD7Snapshot(
        items=items,
        total=total,
        severity_band=severity,
        ready_for_summary=all_locked,
    )
