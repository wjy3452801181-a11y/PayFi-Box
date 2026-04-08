from fastapi import APIRouter

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/")
def agent_placeholder() -> dict[str, str]:
    return {
        "module": "agent",
        "status": "placeholder",
        "message": "Advanced AI orchestration will be added after the rule-based command intake stage.",
    }
