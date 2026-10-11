import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.enums import PaymentStatus
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


def parse_payment_id(raw_id: str | int) -> uuid.UUID | None:
    """id платежа — UUID. Любое другое значение ("999999", 999999) — это id несуществующего
    платежа (404), а не ошибка формата (422): клиент не обязан знать, как устроены наши id."""
    try:
        return uuid.UUID(str(raw_id))
    except ValueError:
        return None


def get_payment(session: Session, raw_id: str | int) -> Payment | None:
    payment_id = parse_payment_id(raw_id)
    if payment_id is None:
        return None
    return session.get(Payment, payment_id)


def list_payments(
    session: Session,
    *,
    email: str | None,
    status: PaymentStatus | None,
    limit: int,
    offset: int,
) -> list[Payment]:
    query = select(Payment)
    if email is not None:
        # Email хранится в нижнем регистре (см. PaymentCreate) — ищем так же.
        query = query.where(Payment.email == email.strip().lower())
    if status is not None:
        query = query.where(Payment.status == status)
    # Новые сначала; id — второй ключ сортировки, чтобы при одинаковом created_at
    # порядок был стабильным и страницы не перемешивались.
    query = query.order_by(Payment.created_at.desc(), Payment.id).limit(limit).offset(offset)
    return list(session.scalars(query))


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
    # PaymentCreate гарантирует: срок задан тогда и только тогда, когда method == installment.
    schedule = None
    if data.installment_months is not None:
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
