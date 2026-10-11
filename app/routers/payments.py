import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.exceptions import RequestValidationError

from app.db import SessionDep
from app.models import Payment
from app.schemas import PaymentCreate, PaymentOut
from app.services import payments as payment_service

router = APIRouter(tags=["payments"])


@router.post("/payments", status_code=status.HTTP_201_CREATED)
def create_payment(data: PaymentCreate, session: SessionDep) -> PaymentOut:
    try:
        payment = payment_service.create_payment(session, data)
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
    return PaymentOut.model_validate(payment)


@router.get("/payments/{payment_id}")
def get_payment(payment_id: uuid.UUID, session: SessionDep) -> PaymentOut:
    payment = session.get(Payment, payment_id)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return PaymentOut.model_validate(payment)
