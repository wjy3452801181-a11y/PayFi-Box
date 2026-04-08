from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN
from typing import Any

from web3 import Web3
from web3.contract import Contract

from app.core.config import Settings


PAYMENT_EXECUTOR_ABI: list[dict[str, Any]] = [
    {
        "inputs": [],
        "name": "operator",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "executionItemId", "type": "bytes32"},
            {"internalType": "bytes32", "name": "orderId", "type": "bytes32"},
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "beneficiary", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "string", "name": "referenceText", "type": "string"},
            {"internalType": "uint256", "name": "splitIndex", "type": "uint256"},
            {"internalType": "uint256", "name": "splitCount", "type": "uint256"},
        ],
        "name": "executePayment",
        "outputs": [{"internalType": "bytes32", "name": "paymentRef", "type": "bytes32"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "orderId", "type": "bytes32"},
            {"internalType": "address", "name": "token", "type": "address"},
            {"internalType": "address", "name": "beneficiary", "type": "address"},
            {"internalType": "uint256", "name": "amount", "type": "uint256"},
            {"internalType": "string", "name": "referenceText", "type": "string"},
            {"internalType": "uint256", "name": "splitIndex", "type": "uint256"},
            {"internalType": "uint256", "name": "splitCount", "type": "uint256"},
        ],
        "name": "executePayment",
        "outputs": [{"internalType": "bytes32", "name": "paymentRef", "type": "bytes32"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "name": "executedItems",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "bytes32", "name": "orderId", "type": "bytes32"},
            {"indexed": True, "internalType": "bytes32", "name": "executionItemId", "type": "bytes32"},
            {"indexed": False, "internalType": "address", "name": "token", "type": "address"},
            {"indexed": True, "internalType": "address", "name": "beneficiary", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "amount", "type": "uint256"},
            {"indexed": False, "internalType": "string", "name": "referenceText", "type": "string"},
            {"indexed": False, "internalType": "uint256", "name": "splitIndex", "type": "uint256"},
            {"indexed": False, "internalType": "uint256", "name": "splitCount", "type": "uint256"},
            {"indexed": False, "internalType": "address", "name": "operator", "type": "address"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"indexed": False, "internalType": "bytes32", "name": "paymentRef", "type": "bytes32"},
        ],
        "name": "PaymentExecuted",
        "type": "event",
    },
]


class HashKeyExecutionError(RuntimeError):
    pass


class HashKeyDuplicateExecutionError(HashKeyExecutionError):
    def __init__(self, message: str, *, execution_item_id: str | None = None) -> None:
        super().__init__(message)
        self.execution_item_id = execution_item_id


@dataclass
class HashKeySubmittedTx:
    tx_hash: str
    explorer_url: str
    sent_at: datetime
    nonce: int
    contract_address: str
    token_address: str
    network: str
    chain_id: int
    execution_item_id: str | None


@dataclass
class HashKeyExecutionResult:
    tx_hash: str
    explorer_url: str
    sent_at: datetime
    confirmed_at: datetime
    gas_used: int | None
    effective_gas_price: int | None
    payment_ref: str | None
    decoded_events: list[dict[str, Any]]
    contract_address: str
    token_address: str
    network: str
    chain_id: int
    nonce: int | None = None
    execution_item_id: str | None = None


class HashKeyExecutionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._validate_settings()
        self.w3 = Web3(Web3.HTTPProvider(self.settings.hashkey_rpc_url, request_kwargs={"timeout": 30}))
        if not self.w3.is_connected():
            raise HashKeyExecutionError(
                f"unable to connect HashKey RPC: {self.settings.hashkey_rpc_url}"
            )

        actual_chain_id = int(self.w3.eth.chain_id)
        if actual_chain_id != int(self.settings.hashkey_chain_id):
            raise HashKeyExecutionError(
                f"chain id mismatch, expected={self.settings.hashkey_chain_id}, got={actual_chain_id}"
            )

        self.account = self.w3.eth.account.from_key(self.settings.hashkey_operator_private_key)
        self.contract_address = self._to_checksum_address(self.settings.hashkey_payment_executor_address)
        self.token_address = self._to_checksum_address(self.settings.hashkey_payment_token_address)
        self.contract = self.w3.eth.contract(
            address=self.contract_address,
            abi=PAYMENT_EXECUTOR_ABI,
        )
        self._validate_contract_operator()
        self.supports_execution_item_id = self._detect_execution_item_support()

    def execute_payment(
        self,
        *,
        order_id: uuid.UUID,
        beneficiary_address: str,
        amount: Decimal,
        reference: str,
        split_index: int,
        split_count: int,
        nonce: int | None = None,
        execution_item_id: uuid.UUID | None = None,
    ) -> HashKeyExecutionResult:
        submitted = self.submit_payment(
            order_id=order_id,
            beneficiary_address=beneficiary_address,
            amount=amount,
            reference=reference,
            split_index=split_index,
            split_count=split_count,
            nonce=nonce,
            execution_item_id=execution_item_id,
        )
        return self.confirm_submitted_payment(
            tx_hash=submitted.tx_hash,
            sent_at=submitted.sent_at,
            nonce=submitted.nonce,
            execution_item_id=submitted.execution_item_id,
        )

    def submit_payment(
        self,
        *,
        order_id: uuid.UUID,
        beneficiary_address: str,
        amount: Decimal,
        reference: str,
        split_index: int,
        split_count: int,
        nonce: int | None = None,
        execution_item_id: uuid.UUID | None = None,
    ) -> HashKeySubmittedTx:
        beneficiary = self._to_checksum_address(beneficiary_address)
        amount_units = self._to_token_units(amount)
        order_id_bytes32 = self._uuid_to_bytes32(order_id)
        sent_at = datetime.now(timezone.utc)
        execution_item_id_bytes32 = self._uuid_to_bytes32(execution_item_id) if execution_item_id else None
        execution_item_id_hex = (
            self._normalize_bytes32(execution_item_id_bytes32)
            if execution_item_id_bytes32 is not None
            else None
        )
        if (
            execution_item_id_bytes32 is not None
            and self.supports_execution_item_id
            and self._is_execution_item_already_executed(execution_item_id_bytes32)
        ):
            raise HashKeyDuplicateExecutionError(
                "execution item already executed onchain",
                execution_item_id=execution_item_id_hex,
            )

        function_call = self._build_execute_payment_function_call(
            order_id_bytes32=order_id_bytes32,
            execution_item_id_bytes32=execution_item_id_bytes32,
            beneficiary=beneficiary,
            amount_units=amount_units,
            reference=reference,
            split_index=split_index,
            split_count=split_count,
        )

        if nonce is None:
            nonce = int(self.w3.eth.get_transaction_count(self.account.address, "pending"))

        tx: dict[str, Any] = {
            "from": self.account.address,
            "chainId": int(self.settings.hashkey_chain_id),
            "nonce": int(nonce),
            "gasPrice": int(self.w3.eth.gas_price),
            "gas": int(self.settings.hashkey_tx_gas_limit),
        }

        try:
            estimated = int(function_call.estimate_gas({"from": self.account.address}))
            tx["gas"] = max(estimated + 20_000, int(self.settings.hashkey_tx_gas_limit))
        except Exception:
            # Keep configured gas limit when estimate is unavailable.
            pass

        built_tx = function_call.build_transaction(tx)
        signed = self.account.sign_transaction(built_tx)
        raw_tx = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction", None)
        if raw_tx is None:
            raise HashKeyExecutionError("failed to sign transaction")

        try:
            tx_hash_bytes = self.w3.eth.send_raw_transaction(raw_tx)
        except Exception as exc:
            if self._is_duplicate_revert(exc):
                raise HashKeyDuplicateExecutionError(
                    "execution item already executed onchain",
                    execution_item_id=execution_item_id_hex,
                ) from exc
            raise HashKeyExecutionError(f"failed to submit transaction: {exc}") from exc
        tx_hash = self._normalize_tx_hash(self.w3.to_hex(tx_hash_bytes))
        explorer_url = self._build_tx_explorer_url(tx_hash)
        return HashKeySubmittedTx(
            tx_hash=tx_hash,
            explorer_url=explorer_url,
            sent_at=sent_at,
            nonce=int(nonce),
            contract_address=self.contract_address,
            token_address=self.token_address,
            network=self.settings.hashkey_network,
            chain_id=int(self.settings.hashkey_chain_id),
            execution_item_id=execution_item_id_hex,
        )

    def confirm_submitted_payment(
        self,
        *,
        tx_hash: str,
        sent_at: datetime,
        nonce: int | None = None,
        execution_item_id: str | None = None,
    ) -> HashKeyExecutionResult:
        tx_hash = self._normalize_tx_hash(tx_hash)
        tx_hash_bytes = Web3.to_bytes(hexstr=tx_hash)
        receipt = self.w3.eth.wait_for_transaction_receipt(
            tx_hash_bytes,
            timeout=int(self.settings.hashkey_tx_timeout_seconds),
        )
        confirmed_at = datetime.now(timezone.utc)
        if int(receipt.status) != 1:
            if execution_item_id and self.supports_execution_item_id:
                try:
                    if self._is_execution_item_already_executed(
                        self._bytes32_hex_to_bytes(execution_item_id)
                    ):
                        raise HashKeyDuplicateExecutionError(
                            "execution item already executed onchain",
                            execution_item_id=execution_item_id,
                        )
                except HashKeyDuplicateExecutionError:
                    raise
                except HashKeyExecutionError:
                    pass
            raise HashKeyExecutionError(f"onchain execution reverted, tx_hash={tx_hash}")

        decoded_events = self._decode_payment_events(contract=self.contract, receipt=receipt)
        payment_ref = decoded_events[0].get("payment_ref") if decoded_events else None
        effective_gas_price = getattr(receipt, "effectiveGasPrice", None)
        explorer_url = self._build_tx_explorer_url(tx_hash)
        return HashKeyExecutionResult(
            tx_hash=tx_hash,
            explorer_url=explorer_url,
            sent_at=sent_at,
            confirmed_at=confirmed_at,
            gas_used=int(receipt.gasUsed) if getattr(receipt, "gasUsed", None) is not None else None,
            effective_gas_price=int(effective_gas_price) if effective_gas_price is not None else None,
            payment_ref=payment_ref,
            decoded_events=decoded_events,
            contract_address=self.contract_address,
            token_address=self.token_address,
            network=self.settings.hashkey_network,
            chain_id=int(self.settings.hashkey_chain_id),
            nonce=nonce,
            execution_item_id=execution_item_id,
        )

    def get_pending_nonce(self) -> int:
        return int(self.w3.eth.get_transaction_count(self.account.address, "pending"))

    def _validate_settings(self) -> None:
        missing = []
        if not self.settings.hashkey_operator_private_key:
            missing.append("HASHKEY_OPERATOR_PRIVATE_KEY")
        if not self.settings.hashkey_payment_executor_address:
            missing.append("HASHKEY_PAYMENT_EXECUTOR_ADDRESS")
        if not self.settings.hashkey_payment_token_address:
            missing.append("HASHKEY_PAYMENT_TOKEN_ADDRESS")
        if missing:
            raise HashKeyExecutionError(
                "missing required HashKey settings: " + ", ".join(missing)
            )

    def _validate_contract_operator(self) -> None:
        try:
            onchain_operator = self.contract.functions.operator().call()
        except Exception as exc:
            raise HashKeyExecutionError(
                f"failed to read contract operator: {exc}"
            ) from exc
        onchain_operator_checksum = self._to_checksum_address(onchain_operator)
        if onchain_operator_checksum != self.account.address:
            raise HashKeyExecutionError(
                "operator wallet mismatch: "
                f"contract.operator={onchain_operator_checksum}, signer={self.account.address}"
            )

    def _detect_execution_item_support(self) -> bool:
        try:
            self.contract.functions.executedItems(b"\x00" * 32).call()
            return True
        except Exception:
            return False

    def _build_execute_payment_function_call(
        self,
        *,
        order_id_bytes32: bytes,
        execution_item_id_bytes32: bytes | None,
        beneficiary: str,
        amount_units: int,
        reference: str,
        split_index: int,
        split_count: int,
    ) -> Any:
        if self.supports_execution_item_id and execution_item_id_bytes32 is not None:
            return self.contract.functions.executePayment(
                execution_item_id_bytes32,
                order_id_bytes32,
                self.token_address,
                beneficiary,
                amount_units,
                reference,
                int(split_index),
                int(split_count),
            )
        return self.contract.functions.executePayment(
            order_id_bytes32,
            self.token_address,
            beneficiary,
            amount_units,
            reference,
            int(split_index),
            int(split_count),
        )

    def _is_execution_item_already_executed(self, execution_item_id_bytes32: bytes) -> bool:
        try:
            executed = self.contract.functions.executedItems(execution_item_id_bytes32).call()
            return bool(executed)
        except Exception as exc:
            raise HashKeyExecutionError(
                f"failed to query executedItems for execution item: {exc}"
            ) from exc

    def _to_checksum_address(self, value: str | None) -> str:
        if not value:
            raise HashKeyExecutionError("address is empty")
        if not Web3.is_address(value):
            raise HashKeyExecutionError(f"invalid address: {value}")
        return Web3.to_checksum_address(value)

    def _to_token_units(self, amount: Decimal) -> int:
        decimals = max(int(self.settings.hashkey_payment_token_decimals), 0)
        multiplier = Decimal(10) ** decimals
        amount_units = (amount * multiplier).quantize(Decimal("1"), rounding=ROUND_DOWN)
        if amount_units <= 0:
            raise HashKeyExecutionError("amount must be positive after token unit conversion")
        return int(amount_units)

    @staticmethod
    def _uuid_to_bytes32(value: uuid.UUID) -> bytes:
        raw = value.bytes
        return raw + b"\x00" * (32 - len(raw))

    @staticmethod
    def _bytes32_hex_to_bytes(value: str) -> bytes:
        normalized = value[2:] if value.startswith("0x") else value
        if len(normalized) != 64:
            raise HashKeyExecutionError(f"invalid bytes32 hex value: {value}")
        try:
            return bytes.fromhex(normalized)
        except ValueError as exc:
            raise HashKeyExecutionError(f"invalid bytes32 hex value: {value}") from exc

    def _build_tx_explorer_url(self, tx_hash: str) -> str:
        return f"{self.settings.hashkey_explorer_base.rstrip('/')}/tx/{self._normalize_tx_hash(tx_hash)}"

    @staticmethod
    def _normalize_tx_hash(value: str) -> str:
        tx_hash = str(value).strip().lower()
        if not tx_hash.startswith("0x"):
            tx_hash = f"0x{tx_hash}"
        return tx_hash

    @staticmethod
    def _is_duplicate_revert(exc: Exception) -> bool:
        candidates = [str(exc), repr(exc)]
        args = getattr(exc, "args", ())
        candidates.extend(str(arg) for arg in args)
        text = " | ".join(candidates).lower()
        if "execution item already executed" in text:
            return True
        return "already executed" in text and "execution item" in text

    @staticmethod
    def _decode_payment_events(*, contract: Contract, receipt: Any) -> list[dict[str, Any]]:
        decoded: list[dict[str, Any]] = []
        try:
            event_rows = contract.events.PaymentExecuted().process_receipt(receipt)
        except Exception:
            return decoded

        for row in event_rows:
            args = dict(row.get("args") or {})
            normalized = {
                "order_id": HashKeyExecutionService._normalize_bytes32(args.get("orderId")),
                "execution_item_id": HashKeyExecutionService._normalize_bytes32(args.get("executionItemId")),
                "token": args.get("token"),
                "beneficiary": args.get("beneficiary"),
                "amount": int(args.get("amount")) if args.get("amount") is not None else None,
                "reference": args.get("referenceText"),
                "split_index": int(args.get("splitIndex")) if args.get("splitIndex") is not None else None,
                "split_count": int(args.get("splitCount")) if args.get("splitCount") is not None else None,
                "operator": args.get("operator"),
                "timestamp": int(args.get("timestamp")) if args.get("timestamp") is not None else None,
                "payment_ref": HashKeyExecutionService._normalize_bytes32(args.get("paymentRef")),
            }
            decoded.append(normalized)
        return decoded

    @staticmethod
    def _normalize_bytes32(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            return "0x" + value.hex()
        try:
            as_hex = value.hex() if hasattr(value, "hex") else str(value)
            if isinstance(as_hex, str) and as_hex.startswith("0x"):
                return as_hex
            return "0x" + as_hex
        except Exception:
            return str(value)
