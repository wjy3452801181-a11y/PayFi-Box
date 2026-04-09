from uuid import UUID

from fastapi import APIRouter, Depends

from app.core.access import get_actor_user_id
from app.db.session import get_db_session
from app.modules.audit.schemas import AuditTraceResponse
from app.modules.audit.service import get_audit_trace

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/{trace_id}", response_model=AuditTraceResponse)
def get_audit_trace_by_id(trace_id: str, actor_user_id: UUID = Depends(get_actor_user_id)) -> AuditTraceResponse:
    with get_db_session() as session:
        return get_audit_trace(session=session, actor_user_id=actor_user_id, trace_id=trace_id)
