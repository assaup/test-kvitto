from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Tariff

# (id, title, price в копейках)
DEFAULT_TARIFFS: tuple[tuple[int, str, int], ...] = (
    (1, "basic", 990_000),  # 9 900 ₽
    (2, "standard", 1_990_000),  # 19 900 ₽
    (3, "premium", 2_990_000),  # 29 900 ₽
)


def seed_tariffs(session: Session) -> None:
    """Создаёт недостающие тарифы. Повторный запуск ничего не дублирует."""
    existing_ids = set(session.scalars(select(Tariff.id)))
    for tariff_id, title, price in DEFAULT_TARIFFS:
        if tariff_id not in existing_ids:
            session.add(Tariff(id=tariff_id, title=title, price=price))
    try:
        session.commit()
    except IntegrityError:
        # Другой процесс (например, второй воркер uvicorn) успел вставить тарифы раньше.
        session.rollback()
