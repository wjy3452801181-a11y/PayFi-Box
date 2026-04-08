from datetime import date
from fastapi import APIRouter
from uuid import UUID

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
) -> ReportSummaryResponse:
    with get_db_session() as session:
        return get_reports_summary(
            session=session,
            user_id=user_id,
            organization_id=organization_id,
            country=country,
            currency=currency,
            risk_level=risk_level,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
