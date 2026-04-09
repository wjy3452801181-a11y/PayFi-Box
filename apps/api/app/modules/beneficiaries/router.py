from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query

from app.core.access import get_actor_user_id, require_actor_user
from app.db.session import get_db_session
from app.modules.beneficiaries.schemas import (
    BeneficiaryDetailResponse,
    BeneficiaryListResponse,
    BeneficiaryPatchRequest,
)
from app.modules.beneficiaries.service import (
    get_beneficiary_detail,
    list_beneficiaries,
    patch_beneficiary,
)

router = APIRouter(prefix="/api/beneficiaries", tags=["beneficiaries"])


@router.get("", response_model=BeneficiaryListResponse)
def get_beneficiaries(
    country: str | None = None,
    risk_level: str | None = None,
    is_blacklisted: bool | None = None,
    name: str | None = None,
    organization_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> BeneficiaryListResponse:
    with get_db_session() as session:
        actor_user = require_actor_user(session, actor_user_id)
        return list_beneficiaries(
            session=session,
            actor_user=actor_user,
            country=country,
            risk_level=risk_level,
            is_blacklisted=is_blacklisted,
            name=name,
            organization_id=organization_id,
            limit=limit,
        )


@router.get("/{beneficiary_id}", response_model=BeneficiaryDetailResponse)
def get_beneficiary_by_id(
    beneficiary_id: UUID,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> BeneficiaryDetailResponse:
    with get_db_session() as session:
        actor_user = require_actor_user(session, actor_user_id)
        return get_beneficiary_detail(session=session, actor_user=actor_user, beneficiary_id=beneficiary_id)


@router.patch("/{beneficiary_id}", response_model=BeneficiaryDetailResponse)
def patch_beneficiary_by_id(
    beneficiary_id: UUID,
    request: BeneficiaryPatchRequest,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> BeneficiaryDetailResponse:
    with get_db_session() as session:
        actor_user = require_actor_user(session, actor_user_id)
        return patch_beneficiary(
            session=session,
            actor_user=actor_user,
            beneficiary_id=beneficiary_id,
            request=request,
        )
