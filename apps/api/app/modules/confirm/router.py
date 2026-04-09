from fastapi import APIRouter, Depends, HTTPException, status
from uuid import UUID

from app.core.access import (
    get_actor_user_id,
    require_command_access,
    require_execution_batch_access,
    require_execution_item_access,
)
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
def post_confirm(request: ConfirmRequest, actor_user_id: UUID = Depends(get_actor_user_id)) -> ConfirmResponse:
    with get_db_session() as session:
        require_command_access(session=session, actor_user_id=actor_user_id, command_id=request.command_id)
        if request.actor_user_id is not None and request.actor_user_id != actor_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="actor_user_id does not match the current actor",
            )
        return handle_confirm(
            session=session,
            request=request.model_copy(update={"actor_user_id": actor_user_id}),
        )


@router.post("/executions/reconcile", response_model=ReconcileExecutionResponse)
def post_reconcile_executions(
    request: ReconcileExecutionRequest,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> ReconcileExecutionResponse:
    with get_db_session() as session:
        if request.execution_batch_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="execution_batch_id is required for reconcile requests",
            )
        require_execution_batch_access(
            session=session,
            actor_user_id=actor_user_id,
            execution_batch_id=request.execution_batch_id,
        )
        return reconcile_execution_batches(session=session, request=request)


@router.post("/execution-items/{execution_item_id}/attach-tx", response_model=ExecutionItemActionResponse)
def post_execution_item_attach_tx(
    execution_item_id: UUID,
    request: AttachExecutionItemTxRequest,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> ExecutionItemActionResponse:
    with get_db_session() as session:
        require_execution_item_access(
            session=session,
            actor_user_id=actor_user_id,
            execution_item_id=execution_item_id,
        )
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
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> ExecutionItemActionResponse:
    with get_db_session() as session:
        require_execution_item_access(
            session=session,
            actor_user_id=actor_user_id,
            execution_item_id=execution_item_id,
        )
        return attach_execution_item_safe_proposal(
            session=session,
            execution_item_id=execution_item_id,
            request=request,
        )


@router.post("/execution-items/{execution_item_id}/sync-receipt", response_model=ExecutionItemActionResponse)
def post_execution_item_sync_receipt(
    execution_item_id: UUID,
    request: SyncExecutionItemReceiptRequest,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> ExecutionItemActionResponse:
    with get_db_session() as session:
        require_execution_item_access(
            session=session,
            actor_user_id=actor_user_id,
            execution_item_id=execution_item_id,
        )
        if request.actor_user_id is not None and request.actor_user_id != actor_user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="actor_user_id does not match the current actor",
            )
        return sync_execution_item_receipt(
            session=session,
            execution_item_id=execution_item_id,
            request=request.model_copy(update={"actor_user_id": actor_user_id}),
        )
