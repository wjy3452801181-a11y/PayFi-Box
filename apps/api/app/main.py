from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import get_settings
from app.modules.mcp import payfi_mcp

settings = get_settings()
_mcp_app = payfi_mcp.streamable_http_app()
_mcp_session_lifespan = None

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Initial backend foundation for PayFi Box.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.mount("/mcp", _mcp_app)


@app.on_event("startup")
async def start_mcp_session_manager() -> None:
    global _mcp_session_lifespan
    if _mcp_session_lifespan is None:
        _mcp_session_lifespan = payfi_mcp.session_manager.run()
        await _mcp_session_lifespan.__aenter__()


@app.on_event("shutdown")
async def stop_mcp_session_manager() -> None:
    global _mcp_session_lifespan
    if _mcp_session_lifespan is not None:
        await _mcp_session_lifespan.__aexit__(None, None, None)
        _mcp_session_lifespan = None


@app.on_event("startup")
def log_execution_config() -> None:
    backend = (settings.payment_execution_backend or "mock").strip().lower()
    if backend in {"hashkey", "onchain"}:
        backend = "hashkey_testnet"

    print(f"execution_backend={backend}")
    print(f"rpc_url={settings.hashkey_rpc_url}")
    print(f"chain_id={settings.hashkey_chain_id}")
    print(f"wallet_loaded={str(settings.hashkey_wallet_loaded).lower()}")
    print(f"contract_configured={str(settings.hashkey_contract_configured).lower()}")

    if backend == "hashkey_testnet" and not settings.hashkey_contract_configured:
        print("warning=HASHKEY_PAYMENT_EXECUTOR_ADDRESS is empty; onchain confirm will not execute until contract is configured.")


@app.get("/", tags=["meta"])
def read_root() -> dict[str, str]:
    return {
        "name": settings.app_name,
        "environment": settings.app_env,
        "status": "bootstrap",
    }
