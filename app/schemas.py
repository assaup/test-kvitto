import uuid
from datetime import datetime
from typing import Literal, Self

from email_validator import EmailNotValidError, validate_email
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    field_validator,
    model_validator,
)

from app.enums import PaymentMethod, PaymentStatus
from app.money import get_discount_percent

# Максимум INTEGER в PostgreSQL. Без верхней границы огромный tariff_id ронял запрос
# с 500 (ошибка БД при выходе числа за диапазон INTEGER) вместо 422.
DB_INT_MAX = 2_147_483_647
INSTALLMENT_MONTHS = (3, 6, 12)


class TariffOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    price: int  # в копейках


class PaymentCreate(BaseModel):
    # extra="forbid": лишние поля (например, amount) — ошибка 422, сумму задаёт только сервер.
    model_config = ConfigDict(extra="forbid")

    # strict на отдельных полях: "2", 2.0 и true не превратятся в int. На всю модель strict ставить
    # нельзя — FastAPI валидирует уже разобранный JSON, и строгий enum не принял бы строку "card".
    tariff_id: int = Field(gt=0, le=DB_INT_MAX, strict=True)
    email: str = Field(max_length=320, json_schema_extra={"format": "email"})
    method: PaymentMethod
    # Не Literal[3, 6, 12]: к Literal нельзя применить strict, и 3.0 проходил бы как 3.
    installment_months: int | None = Field(
        default=None, strict=True, json_schema_extra={"enum": list(INSTALLMENT_MONTHS)}
    )
    promo_code: str | None = Field(default=None, max_length=50)

    @field_validator("email")
    @classmethod
    def validate_email_address(cls, value: str) -> str:
        # Не EmailStr: он молча превращает "Иван <ivan@example.com>" в "ivan@example.com".
        # validate_email по умолчанию не принимает имя перед адресом — это ошибка 422.
        try:
            email = validate_email(value, check_deliverability=False).normalized
        except EmailNotValidError as error:
            raise ValueError(str(error)) from None
        # Целиком в нижнем регистре: Student@example.com и student@example.com — один получатель,
        # и повтор с тем же Idempotency-Key не должен давать 409 из-за регистра.
        return email.lower()

    @field_validator("installment_months")
    @classmethod
    def validate_installment_months_value(cls, value: int | None) -> int | None:
        if value is not None and value not in INSTALLMENT_MONTHS:
            raise ValueError("installment_months must be 3, 6 or 12")
        return value

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
    # payment_id — строка или целое: не-UUID значит «платежа нет» (404), а не 422.
    # StrictInt — чтобы true не превратился в 1; null, 1.5 и объекты — по-прежнему 422.
    payment_id: str | StrictInt
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
