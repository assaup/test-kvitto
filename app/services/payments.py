import hashlib
import json

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums import PaymentMethod
from app.models import Payment, Tariff
from app.money import calculate_price, get_discount_percent, split_into_installments
from app.schemas import PaymentCreate


class TariffNotFoundError(Exception):
    pass


class IdempotencyKeyReusedError(Exception):
    """Тот же Idempotency-Key пришёл с другим телом запроса."""


def request_hash(data: PaymentCreate) -> str:
    """Хэш уже провалидированного тела: "kvitto10" и "KVITTO10" дают одинаковый хэш."""
    canonical = json.dumps(data.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def find_by_idempotency_key(session: Session, key: str) -> Payment | None:
    return session.scalar(select(Payment).where(Payment.idempotency_key == key))


def _replay(existing: Payment, data_hash: str) -> Payment:
    if existing.request_hash != data_hash:
        raise IdempotencyKeyReusedError
    return existing


def create_payment(
    session: Session, data: PaymentCreate, idempotency_key: str | None = None
) -> tuple[Payment, bool]:
    """Создаёт платёж. Возвращает (платёж, создан_ли_новый).

    С Idempotency-Key повторный запрос возвращает уже существующий платёж (created=False).
    """
    data_hash = request_hash(data)
    if idempotency_key is not None:
        existing = find_by_idempotency_key(session, idempotency_key)
        if existing is not None:
            return _replay(existing, data_hash), False

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
        idempotency_key=idempotency_key,
        request_hash=data_hash if idempotency_key is not None else None,
    )
    session.add(payment)
    try:
        session.commit()
    except IntegrityError:
        # Гонка: параллельный запрос с тем же ключом успел закоммитить платёж между нашей
        # проверкой выше и вставкой. Проверка "сначала SELECT" сама по себе не защищает —
        # защищает UNIQUE в БД, а здесь мы отдаём платёж, созданный параллельным запросом.
        session.rollback()
        if idempotency_key is None:
            raise
        existing = find_by_idempotency_key(session, idempotency_key)
        if existing is None:
            raise
        return _replay(existing, data_hash), False
    return payment, True
