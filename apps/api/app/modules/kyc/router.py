from uuid import UUID

from fastapi import APIRouter

from app.db.session import get_db_session
from app.modules.kyc.schemas import KycDetailResponse, KycStartRequest, KycStartResponse
from app.modules.kyc.service import get_kyc_verification, start_kyc_verification

router = APIRouter(prefix="/api/kyc", tags=["kyc"])


@router.post("/start", response_model=KycStartResponse)
def post_kyc_start(request: KycStartRequest) -> KycStartResponse:
    with get_db_session() as session:
        return start_kyc_verification(session=session, request=request)


@router.get("/{kyc_id}", response_model=KycDetailResponse)
def get_kyc_by_id(kyc_id: UUID) -> KycDetailResponse:
    with get_db_session() as session:
        return get_kyc_verification(session=session, kyc_id=kyc_id)
