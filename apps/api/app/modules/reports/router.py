from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from app.core.access import get_actor_user_id, normalize_actor_scoped_user_id, require_actor_user
from app.db.session import get_db_session
from app.modules.reports.schemas import ReportSummaryResponse
from app.modules.reports.service import get_reports_summary

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/summary", response_model=ReportSummaryResponse)
def get_report_summary(
    user_id: UUID | None = None,
    organization_id: UUID | None = None,
    country: str | None = None,
    currency: str | None = None,
    risk_level: str | None = None,
    status: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> ReportSummaryResponse:
    with get_db_session() as session:
        actor_user = require_actor_user(session, actor_user_id)
        scoped_user_id = normalize_actor_scoped_user_id(
            session=session,
            actor_user_id=actor_user_id,
            requested_user_id=user_id,
        )
        scoped_organization_id: UUID | None = None
        if organization_id is not None:
            if actor_user.organization_id is None or organization_id != actor_user.organization_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="requested organization_id does not belong to the current actor",
                )
            scoped_organization_id = organization_id
        return get_reports_summary(
            session=session,
            user_id=scoped_user_id if scoped_organization_id is None else None,
            organization_id=scoped_organization_id,
            country=country,
            currency=currency,
            risk_level=risk_level,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
