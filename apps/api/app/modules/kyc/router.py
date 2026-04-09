from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.access import get_actor_user_id, require_actor_matches_user_id, require_kyc_access
from app.db.session import get_db_session
from app.modules.kyc.schemas import KycDetailResponse, KycStartRequest, KycStartResponse
from app.modules.kyc.service import get_kyc_verification, start_kyc_verification

router = APIRouter(prefix="/api/kyc", tags=["kyc"])


@router.post("/start", response_model=KycStartResponse)
def post_kyc_start(request: KycStartRequest, actor_user_id: UUID = Depends(get_actor_user_id)) -> KycStartResponse:
    with get_db_session() as session:
        require_actor_matches_user_id(
            session=session,
            actor_user_id=actor_user_id,
            expected_user_id=request.subject_id,
            label="kyc subject_id",
        )
        return start_kyc_verification(session=session, request=request)


@router.get("/{kyc_id}", response_model=KycDetailResponse)
def get_kyc_by_id(kyc_id: UUID, actor_user_id: UUID = Depends(get_actor_user_id)) -> KycDetailResponse:
    with get_db_session() as session:
        require_kyc_access(session=session, actor_user_id=actor_user_id, kyc_id=kyc_id)
        return get_kyc_verification(session=session, kyc_id=kyc_id)
