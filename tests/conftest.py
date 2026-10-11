import json
import os
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import create_engine, func, make_url, select, text
from sqlalchemy.exc import OperationalError

from app.config import Settings
from app.main import create_app
from app.models import Payment
from app.signatures import sign

WEBHOOK_SECRET = "test-webhook-secret"
ALEMBIC_INI = Path(__file__).resolve().parent.parent / "alembic.ini"
# Отдельная база для тестов (создаёт docker/postgres-init.sql): тесты очищают таблицы.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://kvitto:kvitto@localhost:5433/kvitto_test"
)


def alembic_config(database_url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.attributes["database_url"] = database_url  # читает migrations/env.py
    return config


@pytest.fixture(scope="session")
def migrated_database() -> str:
    """Тестовая база: схема пересоздаётся миграциями один раз за прогон."""
    url = make_url(TEST_DATABASE_URL)
    safe_url = url.render_as_string(hide_password=True)
    if not (url.database or "").endswith("_test"):
        # Защита от `TRUNCATE` рабочей базы по ошибке в переменной окружения.
        pytest.exit(f"Тесты очищают таблицы: нужна база с суффиксом _test, а не {safe_url}", 2)

    # connect_timeout: без него на Windows ответ «БД недоступна» приходил через ~2 минуты.
    engine = create_engine(TEST_DATABASE_URL, connect_args={"connect_timeout": 3})
    try:
        with engine.connect():
            pass
    except OperationalError:
        pytest.exit(f"PostgreSQL недоступен ({safe_url}): запустите docker compose up -d db", 2)
    finally:
        engine.dispose()

    config = alembic_config(TEST_DATABASE_URL)
    command.downgrade(config, "base")  # чистый старт, даже если прошлый прогон оборвался
    command.upgrade(config, "head")
    return TEST_DATABASE_URL


@pytest.fixture
def database_url(migrated_database: str) -> str:
    """База для одного теста: схема из миграций, таблицы очищены перед тестом."""
    engine = create_engine(migrated_database)
    with engine.begin() as connection:
        connection.execute(text("TRUNCATE payments, tariffs RESTART IDENTITY CASCADE"))
    engine.dispose()
    return migrated_database


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
