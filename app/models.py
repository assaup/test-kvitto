import uuid
from datetime import UTC, datetime
from enum import StrEnum

from sqlalchemy import JSON, CheckConstraint, Enum, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base, UTCDateTime
from app.enums import PaymentMethod, PaymentStatus


def _str_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Хранит в БД значения enum ("pending"), а не имена ("PENDING"), с CHECK-ограничением."""
    return Enum(
        enum_cls,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=20,
        values_callable=lambda members: [member.value for member in members],
    )


class Tariff(Base):
    __tablename__ = "tariffs"
    __table_args__ = (CheckConstraint("price > 0", name="ck_tariffs_price_positive"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(50), unique=True)
    price: Mapped[int] = mapped_column(Integer)  # в копейках


class Payment(Base):
    __tablename__ = "payments"
    __table_args__ = (
        CheckConstraint("amount > 0", name="ck_payments_amount_positive"),
        CheckConstraint("discount >= 0", name="ck_payments_discount_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    status: Mapped[PaymentStatus] = mapped_column(
        _str_enum(PaymentStatus, "payment_status"), default=PaymentStatus.PENDING
    )
    tariff_id: Mapped[int] = mapped_column(ForeignKey("tariffs.id"))
    email: Mapped[str] = mapped_column(String(320))
    method: Mapped[PaymentMethod] = mapped_column(_str_enum(PaymentMethod, "payment_method"))
    installment_months: Mapped[int | None] = mapped_column(Integer)
    amount: Mapped[int] = mapped_column(Integer)  # к оплате, копейки
    discount: Mapped[int] = mapped_column(Integer)  # скидка, копейки
    schedule: Mapped[list[int] | None] = mapped_column(JSON)  # платежи рассрочки, копейки
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=lambda: datetime.now(UTC))
