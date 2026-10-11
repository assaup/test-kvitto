"""Денежные расчёты. Все суммы — целые копейки (int), float не используется нигде."""

from dataclasses import dataclass

# Промокод (в верхнем регистре) → скидка в процентах.
PROMO_CODES: dict[str, int] = {"KVITTO10": 10}


class UnknownPromoCodeError(ValueError):
    """Наследуется от ValueError: в валидаторе Pydantic превращается в стандартный ответ 422."""


@dataclass(frozen=True)
class Price:
    amount: int  # к оплате, копейки
    discount: int  # скидка, копейки


def get_discount_percent(promo_code: str | None) -> int:
    """Скидка в процентах по промокоду. Регистр и пробелы по краям не важны."""
    if promo_code is None or not promo_code.strip():
        return 0
    code = promo_code.strip()
    # Только ASCII: иначе "kvıtto10" (турецкая ı без точки) после upper() стала бы "KVITTO10".
    if not code.isascii() or code.upper() not in PROMO_CODES:
        raise UnknownPromoCodeError(f"Unknown promo code: {promo_code!r}")
    return PROMO_CODES[code.upper()]


def percent_of(amount: int, percent: int) -> int:
    """Процент от суммы в копейках с округлением половины вверх (0.5 коп. → 1 коп.).

    Целочисленная арифметика: (amount * percent) / 100, к числителю добавляем 50,
    чтобы целочисленное деление округляло по правилу ROUND_HALF_UP, а не вниз.
    """
    if amount < 0 or not 0 <= percent <= 100:
        raise ValueError("amount must be >= 0 and percent must be in [0, 100]")
    return (amount * percent + 50) // 100


def calculate_price(tariff_price: int, discount_percent: int) -> Price:
    """Сумма к оплате и скидка. Инвариант: amount + discount == tariff_price."""
    discount = percent_of(tariff_price, discount_percent)
    return Price(amount=tariff_price - discount, discount=discount)


def split_into_installments(amount: int, months: int) -> list[int]:
    """Делит сумму на платежи без потери копеек; лишние копейки уходят в первые платежи.

    1_990_000 на 3 → [663_334, 663_333, 663_333]: сумма ровно 1_990_000.
    """
    if months <= 0:
        raise ValueError("months must be positive")
    if amount < months:
        raise ValueError("amount is too small: every payment must be at least 1 kopeck")
    base, remainder = divmod(amount, months)
    return [base + 1] * remainder + [base] * (months - remainder)
