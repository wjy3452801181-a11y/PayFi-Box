from fastapi import APIRouter
from uuid import UUID

from app.db.session import get_db_session
from app.modules.confirm.schemas import (
    AttachExecutionItemSafeProposalRequest,
    AttachExecutionItemTxRequest,
    ConfirmRequest,
    ConfirmResponse,
    ExecutionItemActionResponse,
    ReconcileExecutionRequest,
    ReconcileExecutionResponse,
    SyncExecutionItemReceiptRequest,
)
from app.modules.confirm.durable_service import (
    attach_execution_item_safe_proposal,
    attach_execution_item_tx,
    handle_confirm,
    reconcile_execution_batches,
    sync_execution_item_receipt,
)

router = APIRouter(prefix="/api", tags=["confirm"])


@router.post("/confirm", response_model=ConfirmResponse)
def post_confirm(request: ConfirmRequest) -> ConfirmResponse:
    with get_db_session() as session:
        return handle_confirm(session=session, request=request)


@router.post("/executions/reconcile", response_model=ReconcileExecutionResponse)
def post_reconcile_executions(request: ReconcileExecutionRequest) -> ReconcileExecutionResponse:
    with get_db_session() as session:
        return reconcile_execution_batches(session=session, request=request)


@router.post("/execution-items/{execution_item_id}/attach-tx", response_model=ExecutionItemActionResponse)
def post_execution_item_attach_tx(
    execution_item_id: UUID,
    request: AttachExecutionItemTxRequest,
) -> ExecutionItemActionResponse:
    with get_db_session() as session:
        return attach_execution_item_tx(
            session=session,
            execution_item_id=execution_item_id,
            request=request,
        )


@router.post(
    "/execution-items/{execution_item_id}/attach-safe-proposal",
    response_model=ExecutionItemActionResponse,
)
def post_execution_item_attach_safe_proposal(
    execution_item_id: UUID,
    request: AttachExecutionItemSafeProposalRequest,
) -> ExecutionItemActionResponse:
    with get_db_session() as session:
        return attach_execution_item_safe_proposal(
            session=session,
            execution_item_id=execution_item_id,
            request=request,
        )


@router.post("/execution-items/{execution_item_id}/sync-receipt", response_model=ExecutionItemActionResponse)
def post_execution_item_sync_receipt(
    execution_item_id: UUID,
    request: SyncExecutionItemReceiptRequest,
) -> ExecutionItemActionResponse:
    with get_db_session() as session:
        return sync_execution_item_receipt(
            session=session,
            execution_item_id=execution_item_id,
            request=request,
        )
