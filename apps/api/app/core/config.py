from functools import lru_cache

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    app_name: str = "PayFi Box API"
    app_env: str = "development"
    app_port: int = 8000
    database_url: str = "postgresql://localhost:5432/payfi_box"
    database_echo: bool = False
    cors_allow_origins: list[str] = Field(
        default_factory=lambda: [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]
    )
    payment_execution_backend: str = "mock"
    hashkey_network: str = "hashkey_testnet"
    hashkey_rpc_url: str = "https://testnet.hsk.xyz"
    hashkey_chain_id: int = 133
    hashkey_explorer_base: str = "https://testnet-explorer.hsk.xyz"
    hashkey_operator_private_key: str | None = None
    hashkey_payment_executor_address: str | None = None
    hashkey_payment_token_address: str | None = None
    hashkey_safe_address: str | None = None
    hashkey_payment_token_decimals: int = 18
    hashkey_tx_timeout_seconds: int = 120
    hashkey_tx_gas_limit: int = 450000
    settlement_quote_ttl_seconds: int = 900
    settlement_spread_bps: int = 45
    settlement_platform_fee_bps: int = 30
    settlement_min_platform_fee: float = 0.10
    settlement_network_fee: float = 0.35
    settlement_fiat_channel: str = "stripe"
    settlement_require_kyc: bool = True
    settlement_kyc_provider: str = "stripe_identity"
    settlement_kyc_demo_mode: bool = False
    settlement_allow_manual_mark_received_override: bool = False
    stripe_secret_key: str | None = None
    stripe_webhook_secret: str | None = None
    stripe_checkout_success_url: str = "http://localhost:3000/merchant?stripe=success"
    stripe_checkout_cancel_url: str = "http://localhost:3000/merchant?stripe=cancel"
    stripe_identity_return_url: str = "http://localhost:3000/merchant?kyc=done"

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def parse_cors_allow_origins(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return value
        raise ValueError("CORS_ALLOW_ORIGINS must be a comma-separated string or list")

    @model_validator(mode="after")
    def validate_hashkey_backend_requirements(self) -> "Settings":
        backend = (self.payment_execution_backend or "").strip().lower()
        if backend in {"hashkey", "hashkey_testnet", "onchain"}:
            if not (self.hashkey_rpc_url or "").strip():
                raise ValueError(
                    "HASHKEY_RPC_URL is required when PAYMENT_EXECUTION_BACKEND=hashkey_testnet"
                )
            if not (self.hashkey_operator_private_key or "").strip():
                raise ValueError(
                    "HASHKEY_OPERATOR_PRIVATE_KEY is required when PAYMENT_EXECUTION_BACKEND=hashkey_testnet"
                )
        return self

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url

    @property
    def hashkey_wallet_loaded(self) -> bool:
        value = (self.hashkey_operator_private_key or "").strip()
        if not value:
            return False
        placeholder_markers = (
            "REPLACE_WITH_YOUR_PRIVATE_KEY",
            "YOUR_PRIVATE_KEY_HERE",
            "0xYOUR_TESTNET_OPERATOR_PRIVATE_KEY",
        )
        return value not in placeholder_markers

    @property
    def hashkey_contract_configured(self) -> bool:
        return bool((self.hashkey_payment_executor_address or "").strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
