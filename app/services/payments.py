from sqlalchemy.orm import Session

from app.enums import PaymentMethod
from app.models import Payment, Tariff
from app.money import calculate_price, get_discount_percent, split_into_installments
from app.schemas import PaymentCreate


class TariffNotFoundError(Exception):
    pass


def create_payment(session: Session, data: PaymentCreate) -> Payment:
    tariff = session.get(Tariff, data.tariff_id)
    if tariff is None:
        raise TariffNotFoundError(data.tariff_id)

    # Сумму всегда считает сервер по цене тарифа из БД — клиент её не передаёт.
    price = calculate_price(tariff.price, get_discount_percent(data.promo_code))
    schedule = None
    if data.method is PaymentMethod.INSTALLMENT:
        assert data.installment_months is not None  # гарантирует PaymentCreate
        schedule = split_into_installments(price.amount, data.installment_months)

    payment = Payment(
        tariff_id=tariff.id,
        email=data.email,
        method=data.method,
        installment_months=data.installment_months,
        amount=price.amount,
        discount=price.discount,
        schedule=schedule,
    )
    session.add(payment)
    session.commit()
    return payment
