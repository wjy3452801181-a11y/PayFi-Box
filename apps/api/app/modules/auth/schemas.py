from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel


class AccessSessionRequest(BaseModel):
    email: str
    access_code: str


class AccessSessionUserView(BaseModel):
    id: UUID
    name: str
    email: str
    role: str
    organization_id: UUID | None = None


class AccessSessionResponse(BaseModel):
    user: AccessSessionUserView
    access_token: str
    expires_at: datetime
