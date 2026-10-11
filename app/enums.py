from enum import StrEnum


class PaymentMethod(StrEnum):
    CARD = "card"
    SBP = "sbp"
    INSTALLMENT = "installment"


class PaymentStatus(StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    REFUNDED = "refunded"


# Допустимые переходы статусов. Всё, чего здесь нет, запрещено (в т.ч. в тот же статус).
ALLOWED_TRANSITIONS: dict[PaymentStatus, frozenset[PaymentStatus]] = {
    PaymentStatus.PENDING: frozenset({PaymentStatus.SUCCEEDED, PaymentStatus.FAILED}),
    PaymentStatus.SUCCEEDED: frozenset({PaymentStatus.REFUNDED}),
    PaymentStatus.FAILED: frozenset(),
    PaymentStatus.REFUNDED: frozenset(),
}


def statuses_allowed_to_become(target: PaymentStatus) -> list[PaymentStatus]:
    """Из каких статусов можно перейти в target: succeeded ← [pending], refunded ← [succeeded]."""
    return [source for source, targets in ALLOWED_TRANSITIONS.items() if target in targets]
