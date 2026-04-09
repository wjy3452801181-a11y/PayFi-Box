from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import issue_access_token, verify_access_code
from app.db.models import User, UserAccessCredential
from app.modules.auth.schemas import (
    AccessSessionRequest,
    AccessSessionResponse,
    AccessSessionUserView,
)


def create_access_session(session: Session, request: AccessSessionRequest) -> AccessSessionResponse:
    normalized_email = request.email.strip().lower()
    if not normalized_email:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="email is required")
    if not request.access_code.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="access_code is required")

    user = session.execute(
        select(User).where(User.email == normalized_email).limit(1)
    ).scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    credential = session.execute(
        select(UserAccessCredential)
        .where(
            UserAccessCredential.user_id == user.id,
            UserAccessCredential.is_active.is_(True),
        )
        .limit(1)
    ).scalar_one_or_none()
    if credential is None or not verify_access_code(request.access_code, credential.access_code_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials")

    credential.last_used_at = datetime.now(timezone.utc)
    session.add(credential)
    session.commit()
    access_token, expires_at = issue_access_token(user)
    return AccessSessionResponse(
        user=AccessSessionUserView(
            id=user.id,
            name=user.name,
            email=user.email,
            role=user.role,
            organization_id=user.organization_id,
        ),
        access_token=access_token,
        expires_at=expires_at,
    )
