import json
import shutil
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import func, select

from app.config import Settings
from app.main import create_app
from app.models import Payment
from app.signatures import sign

WEBHOOK_SECRET = "test-webhook-secret"
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"


def alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = database_url  # читает migrations/env.py
    return config


def run_migrations(database_url: str) -> None:
    command.upgrade(alembic_config(database_url), "head")


@pytest.fixture(scope="session")
def migrated_db_template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Схема из миграций — та же, что в продакшене. Создаётся один раз на все тесты."""
    path = tmp_path_factory.mktemp("template") / "template.db"
    run_migrations(f"sqlite:///{path}")
    return path


@pytest.fixture
def database_url(tmp_path: Path, migrated_db_template: Path) -> str:
    """Каждому тесту — своя копия мигрированной БД. Файловая SQLite (а не :memory:) —
    чтобы потоки в конкурентных тестах видели одну БД."""
    path = tmp_path / "test.db"
    shutil.copy(migrated_db_template, path)
    return f"sqlite:///{path}"


def make_settings(database_url: str, webhook_secret: str | None = WEBHOOK_SECRET) -> Settings:
    """Явные настройки для тестов — не зависят от локального .env разработчика."""
    return Settings(database_url=database_url, webhook_secret=webhook_secret)


@pytest.fixture
def client(database_url: str) -> Iterator[TestClient]:
    with TestClient(create_app(make_settings(database_url))) as test_client:  # запуск lifespan
        yield test_client


def signed_headers(body: bytes, secret: str = WEBHOOK_SECRET) -> dict[str, str]:
    return {"Content-Type": "application/json", "X-Signature": sign(secret, body)}


def send_webhook(client: TestClient, payment_id: str | int, status: str) -> Response:
    """Подписанный вебхук банка."""
    body = json.dumps({"payment_id": payment_id, "status": status}).encode()
    return client.post("/webhooks/bank", content=body, headers=signed_headers(body))


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
