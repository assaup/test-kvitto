from fastapi import APIRouter, HTTPException, status

from app.db import SessionDep
from app.errors import ApiError
from app.schemas import BankWebhook, WebhookAck
from app.services import webhooks as webhook_service

router = APIRouter(tags=["webhooks"])


@router.post(
    "/webhooks/bank",
    responses={
        404: {"description": "Платёж не найден"},
        409: {"description": 'Запрещённый переход статуса: {"error": "invalid_transition"}'},
    },
)
def bank_webhook(data: BankWebhook, session: SessionDep) -> WebhookAck:
    try:
        webhook_service.change_status(session, data.payment_id, data.status)
    except webhook_service.PaymentNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found"
        ) from None
    except webhook_service.InvalidTransitionError:
        raise ApiError(status.HTTP_409_CONFLICT, "invalid_transition") from None
    return WebhookAck()
