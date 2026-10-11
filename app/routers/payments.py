from typing import Annotated

from fastapi import APIRouter, Header, Query, Response, status
from fastapi.exceptions import RequestValidationError

from app.db import SessionDep
from app.enums import PaymentStatus
from app.errors import ApiError
from app.schemas import DB_INT_MAX, PaymentCreate, PaymentOut
from app.services import payments as payment_service

router = APIRouter(tags=["payments"])

IdempotencyKeyHeader = Annotated[
    str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)
]


@router.post(
    "/payments",
    status_code=status.HTTP_201_CREATED,
    responses={
        200: {"description": "Повтор с тем же Idempotency-Key: возвращён существующий платёж"},
        409: {"description": "Idempotency-Key уже использован с другим телом запроса"},
    },
)
def create_payment(
    data: PaymentCreate,
    session: SessionDep,
    response: Response,
    idempotency_key: IdempotencyKeyHeader = None,
) -> PaymentOut:
    try:
        payment, created = payment_service.create_payment(session, data, idempotency_key)
    except payment_service.TariffNotFoundError:
        # Ошибка в теле запроса → 422 в стандартном формате FastAPI, как и остальная валидация.
        raise RequestValidationError(
            [
                {
                    "type": "tariff_not_found",
                    "loc": ("body", "tariff_id"),
                    "msg": "Tariff not found",
                    "input": data.tariff_id,
                }
            ]
        ) from None
    except payment_service.IdempotencyKeyReusedError:
        raise ApiError(status.HTTP_409_CONFLICT, "idempotency_key_reused") from None

    if not created:
        response.status_code = status.HTTP_200_OK
    return PaymentOut.model_validate(payment)


@router.get("/payments")
def list_payments(
    session: SessionDep,
    email: Annotated[str | None, Query(max_length=320)] = None,
    # Параметр называется payment_status, чтобы не перекрыть модуль fastapi.status;
    # в URL он по-прежнему ?status=...
    payment_status: Annotated[PaymentStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    # Верхняя граница: огромный offset иначе ронял бы запрос в БД с 500 вместо 422.
    offset: Annotated[int, Query(ge=0, le=DB_INT_MAX)] = 0,
) -> list[PaymentOut]:
    payments = payment_service.list_payments(
        session, email=email, status=payment_status, limit=limit, offset=offset
    )
    return [PaymentOut.model_validate(payment) for payment in payments]


@router.get(
    "/payments/{payment_id}",
    responses={404: {"description": 'Платёж не найден: {"error": "payment_not_found"}'}},
)
def get_payment(payment_id: str, session: SessionDep) -> PaymentOut:
    # payment_id — строка, а не uuid.UUID: на "999999" отвечаем 404 «нет такого», а не 422.
    payment = payment_service.get_payment(session, payment_id)
    if payment is None:
        raise ApiError(status.HTTP_404_NOT_FOUND, "payment_not_found")
    return PaymentOut.model_validate(payment)
