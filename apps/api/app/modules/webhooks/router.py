from __future__ import annotations

from fastapi import APIRouter, Header, Request

from app.db.session import get_db_session
from app.modules.merchant.service import handle_stripe_webhook

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def post_stripe_webhook(
    request: Request,
    stripe_signature: str | None = Header(default=None, alias="Stripe-Signature"),
) -> dict:
    payload = await request.body()
    with get_db_session() as session:
        return handle_stripe_webhook(
            session=session,
            payload=payload,
            stripe_signature=stripe_signature,
        )
