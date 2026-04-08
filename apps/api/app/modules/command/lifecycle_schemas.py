from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.modules.command.schemas import CommandIntent, QuotePreview, RiskPreview


class CommandTimelineItem(BaseModel):
    timestamp: datetime
    title: str
    action: str
    entity_type: str
    entity_id: UUID
    details: dict[str, Any] | None = None


class CommandTimelineResponse(BaseModel):
    command_id: UUID
    trace_id: str
    count: int
    items: list[CommandTimelineItem]


class CommandReplayResponse(BaseModel):
    mode: Literal["replay"]
    source_command_id: UUID
    replayed_at: datetime
    session_id: UUID
    user_id: UUID
    status: Literal["ok", "needs_clarification"]
    intent: CommandIntent
    confidence: float = Field(ge=0.0, le=1.0)
    preview: dict[str, Any]
    missing_fields: list[str]
    follow_up_question: str | None = None
    risk: RiskPreview | None = None
    quote: QuotePreview | None = None
    next_action: str
    message: str
