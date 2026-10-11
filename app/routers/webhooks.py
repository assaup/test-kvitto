from collections.abc import Awaitable, Callable

from fastapi import APIRouter, Request, Response, status
from fastapi.routing import APIRoute

from app.db import SessionDep
from app.errors import ApiError
from app.schemas import BankWebhook, WebhookAck
from app.services import webhooks as webhook_service
from app.signatures import is_valid_signature


class SignedWebhookRoute(APIRoute):
    """Маршрут, который проверяет X-Signature ДО того, как FastAPI разберёт тело.

    Через Depends так сделать нельзя: FastAPI разбирает JSON раньше зависимостей, и
    неподписанный битый JSON получал бы 422 вместо 401. Здесь подпись считается по сырым
    байтам тела — ровно тем, что подписал банк, — и только потом вызывается обычный обработчик.
    """

    def get_route_handler(self) -> Callable[[Request], Awaitable[Response]]:
        handle = super().get_route_handler()

        async def handle_signed(request: Request) -> Response:
            body = await request.body()  # Starlette кэширует тело: обработчик прочитает его же
            secret = request.app.state.settings.webhook_secret
            if not is_valid_signature(secret, body, request.headers.get("X-Signature")):
                raise ApiError(status.HTTP_401_UNAUTHORIZED, "invalid_signature")
            return await handle(request)

        return handle_signed


router = APIRouter(tags=["webhooks"], route_class=SignedWebhookRoute)

# Заголовок проверяет SignedWebhookRoute, а не параметр функции, поэтому в Swagger
# описываем его вручную.
SIGNATURE_HEADER_DOC = {
    "name": "X-Signature",
    "in": "header",
    "required": True,
    "description": "HMAC-SHA256 от сырого тела запроса с секретом WEBHOOK_SECRET, в hex",
    "schema": {"type": "string"},
}


@router.post(
    "/webhooks/bank",
    openapi_extra={"parameters": [SIGNATURE_HEADER_DOC]},
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
