from fastapi import APIRouter

router = APIRouter(prefix="/risk", tags=["risk"])


@router.get("/")
def risk_placeholder() -> dict[str, str]:
    return {
        "module": "risk",
        "status": "placeholder",
        "message": "Expanded policy checks and review orchestration will be added in the next step.",
    }
