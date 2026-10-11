import uuid
from datetime import datetime
from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator, model_validator

from app.enums import PaymentMethod, PaymentStatus
from app.money import get_discount_percent


class TariffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    price: int  # в копейках


class PaymentCreate(BaseModel):
    # extra="forbid": лишние поля (например, amount) — ошибка 422, сумму задаёт только сервер.
    model_config = ConfigDict(extra="forbid")

    # strict только здесь: "2" и true не превратятся в int. На всю модель strict ставить нельзя —
    # FastAPI валидирует уже разобранный JSON, и строгий enum не принял бы строку "card".
    tariff_id: int = Field(gt=0, strict=True)
    email: EmailStr = Field(max_length=320)
    method: PaymentMethod
    installment_months: Literal[3, 6, 12] | None = None
    promo_code: str | None = Field(default=None, max_length=50)

    @field_validator("promo_code")
    @classmethod
    def validate_promo_code(cls, value: str | None) -> str | None:
        get_discount_percent(value)  # неизвестный код → UnknownPromoCodeError(ValueError) → 422
        if value is None or not value.strip():
            return None
        return value.strip().upper()

    @model_validator(mode="after")
    def validate_installment_months(self) -> Self:
        if self.method is PaymentMethod.INSTALLMENT and self.installment_months is None:
            raise ValueError("installment_months is required for installment method")
        if self.method is not PaymentMethod.INSTALLMENT and self.installment_months is not None:
            raise ValueError("installment_months is allowed only for installment method")
        return self


class BankWebhook(BaseModel):
    # Лишние поля не запрещаем: банк может присылать дополнительные данные.
    payment_id: uuid.UUID
    status: PaymentStatus


class WebhookAck(BaseModel):
    result: Literal["ok"] = "ok"


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: PaymentStatus
    tariff_id: int
    amount: int  # к оплате, копейки
    discount: int  # скидка, копейки
    method: PaymentMethod
    installment_months: int | None
    schedule: list[int] | None  # платежи рассрочки в копейках, для card/sbp — null
    email: str
    created_at: datetime
