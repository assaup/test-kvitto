from sqlalchemy import update
from sqlalchemy.orm import Session

from app.enums import PaymentStatus, statuses_allowed_to_become
from app.models import Payment
from app.services.payments import parse_payment_id


class PaymentNotFoundError(Exception):
    pass


class InvalidTransitionError(Exception):
    pass


def change_status(session: Session, raw_payment_id: str | int, new_status: PaymentStatus) -> None:
    """Меняет статус платежа, если переход разрешён.

    Проверка и запись — один UPDATE с условием на текущий статус (compare-and-set).
    Вариант «прочитать статус → проверить в Python → записать» небезопасен: два параллельных
    вебхука (succeeded и failed) оба прочитали бы pending и оба записали бы свой статус.
    Здесь БД выполняет UPDATE атомарно, и выиграет ровно один из них.
    """
    payment_id = parse_payment_id(raw_payment_id)
    if payment_id is None:
        raise PaymentNotFoundError(raw_payment_id)

    result = session.execute(
        update(Payment)
        .where(
            Payment.id == payment_id,
            Payment.status.in_(statuses_allowed_to_become(new_status)),
        )
        .values(status=new_status)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount == 1:
        session.commit()
        return

    session.rollback()
    # Ничего не обновилось: либо платежа нет, либо переход из текущего статуса запрещён.
    if session.get(Payment, payment_id) is None:
        raise PaymentNotFoundError(payment_id)
    raise InvalidTransitionError
