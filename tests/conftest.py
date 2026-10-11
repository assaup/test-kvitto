from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.config import Settings
from app.main import create_app
from app.models import Payment
from app.signatures import sign

WEBHOOK_SECRET = "test-webhook-secret"


def make_settings(tmp_path: Path, webhook_secret: str | None = WEBHOOK_SECRET) -> Settings:
    """Явные настройки для тестов — не зависят от локального .env разработчика."""
    # Файловая SQLite (а не :memory:) — чтобы потоки в конкурентных тестах видели одну БД.
    return Settings(database_url=f"sqlite:///{tmp_path / 'test.db'}", webhook_secret=webhook_secret)


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(tmp_path))) as test_client:  # with запускает lifespan
        yield test_client


def signed_headers(body: bytes, secret: str = WEBHOOK_SECRET) -> dict[str, str]:
    return {"Content-Type": "application/json", "X-Signature": sign(secret, body)}


@pytest.fixture
def count_payments(client: TestClient) -> Callable[[], int]:
    """Сколько платежей реально лежит в БД — проверяем результат, а не только ответ API."""

    def _count() -> int:
        with client.app.state.session_factory() as session:
            return session.scalar(select(func.count()).select_from(Payment))

    return _count


def payment_payload(**overrides: Any) -> dict[str, Any]:
    """Валидное тело POST /payments с переопределёнными полями.

    Значение None отправляется как JSON null, а не удаляет поле — для удаления используйте del.
    """
    payload: dict[str, Any] = {"tariff_id": 2, "email": "student@example.com", "method": "card"}
    payload.update(overrides)
    return payload
