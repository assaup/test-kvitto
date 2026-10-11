from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status

from app.db import SessionDep
from app.errors import ApiError
from app.schemas import BankWebhook, WebhookAck
from app.services import webhooks as webhook_service
from app.signatures import is_valid_signature

router = APIRouter(tags=["webhooks"])


async def verify_signature(
    request: Request,
    x_signature: Annotated[str | None, Header(alias="X-Signature")] = None,
) -> None:
    """Проверяет подпись по сырым байтам тела — ровно тем, что подписал банк.

    Зависимость выполняется до валидации тела, поэтому неподписанный запрос получает 401,
    а не подсказку 422 о том, какие поля неверны.
    """
    body = await request.body()
    if not is_valid_signature(request.app.state.settings.webhook_secret, body, x_signature):
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "invalid_signature")


@router.post(
    "/webhooks/bank",
    dependencies=[Depends(verify_signature)],
    responses={
        401: {"description": 'Неверная или отсутствующая подпись: {"error": "invalid_signature"}'},
        404: {"description": 'Платёж не найден: {"error": "payment_not_found"}'},
        409: {"description": 'Запрещённый переход статуса: {"error": "invalid_transition"}'},
    },
)
def bank_webhook(data: BankWebhook, session: SessionDep) -> WebhookAck:
    try:
        webhook_service.change_status(session, data.payment_id, data.status)
    except webhook_service.PaymentNotFoundError:
        raise ApiError(status.HTTP_404_NOT_FOUND, "payment_not_found") from None
    except webhook_service.InvalidTransitionError:
        raise ApiError(status.HTTP_409_CONFLICT, "invalid_transition") from None
    return WebhookAck()
