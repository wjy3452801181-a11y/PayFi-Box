from fastapi import APIRouter, Query
from typing import Literal
from uuid import UUID

from app.db.session import get_db_session
from app.modules.command.lifecycle_schemas import CommandReplayResponse, CommandTimelineResponse
from app.modules.command.lifecycle_service import get_command_timeline, replay_command
from app.modules.command.query_schemas import CommandDetailResponse, CommandListResponse
from app.modules.command.query_service import get_command_detail, list_commands
from app.modules.command.schemas import CommandRequest, CommandResponse
from app.modules.command.service import handle_command

router = APIRouter(prefix="/api", tags=["command"])


@router.post("/command", response_model=CommandResponse)
def post_command(request: CommandRequest) -> CommandResponse:
    with get_db_session() as session:
        return handle_command(session=session, request=request)


@router.get("/commands", response_model=CommandListResponse)
def get_commands(
    intent: str | None = None,
    final_status: str | None = None,
    user_id: UUID | None = None,
    session_id: UUID | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    sort_by: Literal["created_at", "final_status"] = "created_at",
    sort_order: Literal["asc", "desc"] = "desc",
) -> CommandListResponse:
    with get_db_session() as session:
        return list_commands(
            session=session,
            intent=intent,
            final_status=final_status,
            user_id=user_id,
            session_id=session_id,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )


@router.get("/commands/{command_id}", response_model=CommandDetailResponse)
def get_command_by_id(command_id: UUID) -> CommandDetailResponse:
    with get_db_session() as session:
        return get_command_detail(session=session, command_id=command_id)


@router.get("/commands/{command_id}/timeline", response_model=CommandTimelineResponse)
def get_command_timeline_by_id(command_id: UUID) -> CommandTimelineResponse:
    with get_db_session() as session:
        return get_command_timeline(session=session, command_id=command_id)


@router.post("/commands/{command_id}/replay", response_model=CommandReplayResponse)
def replay_command_by_id(command_id: UUID) -> CommandReplayResponse:
    with get_db_session() as session:
        return replay_command(session=session, command_id=command_id)
