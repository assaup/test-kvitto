import uuid
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Response, status
from fastapi.exceptions import RequestValidationError

from app.db import SessionDep
from app.errors import ApiError
from app.models import Payment
from app.schemas import PaymentCreate, PaymentOut
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


@router.get("/payments/{payment_id}")
def get_payment(payment_id: uuid.UUID, session: SessionDep) -> PaymentOut:
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return PaymentOut.model_validate(payment)
