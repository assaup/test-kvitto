from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import create_app
from app.models import Payment


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    # Файловая SQLite (а не :memory:) — чтобы потоки в конкурентных тестах видели одну БД.
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(app) as test_client:  # with запускает lifespan: создание таблиц
        yield test_client


@pytest.fixture
def count_payments(client: TestClient) -> Callable[[], int]:
    """Сколько платежей реально лежит в БД — проверяем результат, а не только ответ API."""

    def _count() -> int:
        with client.app.state.session_factory() as session:
            return session.scalar(select(func.count()).select_from(Payment))

    return _count


def payment_payload(**overrides: Any) -> dict[str, Any]:
    """Валидное тело POST /payments; поля можно переопределить или удалить (значение None)."""
    payload: dict[str, Any] = {"tariff_id": 2, "email": "student@example.com", "method": "card"}
    payload.update(overrides)
    return payload
