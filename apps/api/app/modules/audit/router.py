from fastapi import APIRouter

from app.db.session import get_db_session
from app.modules.audit.schemas import AuditTraceResponse
from app.modules.audit.service import get_audit_trace

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/{trace_id}", response_model=AuditTraceResponse)
def get_audit_trace_by_id(trace_id: str) -> AuditTraceResponse:
    with get_db_session() as session:
        return get_audit_trace(session=session, trace_id=trace_id)
