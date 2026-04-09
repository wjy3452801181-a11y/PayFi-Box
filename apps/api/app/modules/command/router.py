from fastapi import APIRouter, Depends, Query
from typing import Literal
from uuid import UUID

from app.core.access import get_actor_user_id, normalize_actor_scoped_user_id, require_command_access, require_actor_matches_user_id
from app.db.session import get_db_session
from app.modules.command.lifecycle_schemas import CommandReplayResponse, CommandTimelineResponse
from app.modules.command.lifecycle_service import get_command_timeline, replay_command
from app.modules.command.query_schemas import CommandDetailResponse, CommandListResponse
from app.modules.command.query_service import get_command_detail, list_commands
from app.modules.command.schemas import CommandRequest, CommandResponse
from app.modules.command.service import handle_command

router = APIRouter(prefix="/api", tags=["command"])


@router.post("/command", response_model=CommandResponse)
def post_command(request: CommandRequest, actor_user_id: UUID = Depends(get_actor_user_id)) -> CommandResponse:
    with get_db_session() as session:
        require_actor_matches_user_id(
            session=session,
            actor_user_id=actor_user_id,
            expected_user_id=request.user_id,
            label="command request user_id",
        )
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
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> CommandListResponse:
    with get_db_session() as session:
        scoped_user_id = normalize_actor_scoped_user_id(
            session=session,
            actor_user_id=actor_user_id,
            requested_user_id=user_id,
        )
        return list_commands(
            session=session,
            intent=intent,
            final_status=final_status,
            user_id=scoped_user_id,
            session_id=session_id,
            limit=limit,
            sort_by=sort_by,
            sort_order=sort_order,
        )


@router.get("/commands/{command_id}", response_model=CommandDetailResponse)
def get_command_by_id(command_id: UUID, actor_user_id: UUID = Depends(get_actor_user_id)) -> CommandDetailResponse:
    with get_db_session() as session:
        require_command_access(session=session, actor_user_id=actor_user_id, command_id=command_id)
        return get_command_detail(session=session, command_id=command_id)


@router.get("/commands/{command_id}/timeline", response_model=CommandTimelineResponse)
def get_command_timeline_by_id(
    command_id: UUID,
    actor_user_id: UUID = Depends(get_actor_user_id),
) -> CommandTimelineResponse:
    with get_db_session() as session:
        require_command_access(session=session, actor_user_id=actor_user_id, command_id=command_id)
        return get_command_timeline(session=session, command_id=command_id)


@router.post("/commands/{command_id}/replay", response_model=CommandReplayResponse)
def replay_command_by_id(command_id: UUID, actor_user_id: UUID = Depends(get_actor_user_id)) -> CommandReplayResponse:
    with get_db_session() as session:
        require_command_access(session=session, actor_user_id=actor_user_id, command_id=command_id)
        return replay_command(session=session, command_id=command_id)
