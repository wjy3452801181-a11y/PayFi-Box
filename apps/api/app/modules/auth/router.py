from __future__ import annotations

from fastapi import APIRouter

from app.db.session import get_db_session
from app.modules.auth.schemas import AccessSessionRequest, AccessSessionResponse
from app.modules.auth.service import create_access_session

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/session", response_model=AccessSessionResponse)
def post_access_session(request: AccessSessionRequest) -> AccessSessionResponse:
    with get_db_session() as session:
        return create_access_session(session=session, request=request)
