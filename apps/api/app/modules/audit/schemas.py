from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel


class AuditTimelineItem(BaseModel):
    timestamp: datetime
    title: str
    action: str
    actor_user_id: UUID | None = None
    entity_type: str
    entity_id: UUID
    before_json: dict[str, Any] | None = None
    after_json: dict[str, Any] | None = None
    details: dict[str, Any] | None = None


class AuditTraceResponse(BaseModel):
    trace_id: str
    count: int
    items: list[AuditTimelineItem]
