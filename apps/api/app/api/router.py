from fastapi import APIRouter

from app.modules.command.router import router as command_router
from app.modules.confirm.router import router as confirm_router
from app.modules.agent.router import router as agent_router
from app.modules.audit.router import router as audit_router
from app.modules.beneficiaries.router import router as beneficiaries_router
from app.modules.payments.router import router as payments_router
from app.modules.reports.router import router as reports_router
from app.modules.risk.router import router as risk_router
from app.modules.merchant.router import router as merchant_router
from app.modules.kyc.router import router as kyc_router
from app.modules.webhooks.router import router as webhooks_router
from app.modules.balance.router import router as balance_router

api_router = APIRouter()
v1_router = APIRouter(prefix="/api/v1")


@api_router.get("/health", tags=["health"])
def health_check() -> dict[str, str]:
    return {"status": "ok", "service": "payfi-box-api"}


v1_router.include_router(risk_router)
v1_router.include_router(agent_router)

api_router.include_router(v1_router)
api_router.include_router(command_router)
api_router.include_router(confirm_router)
api_router.include_router(payments_router)
api_router.include_router(reports_router)
api_router.include_router(audit_router)
api_router.include_router(beneficiaries_router)
api_router.include_router(merchant_router)
api_router.include_router(kyc_router)
api_router.include_router(webhooks_router)
api_router.include_router(balance_router)
