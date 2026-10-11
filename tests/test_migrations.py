from pathlib import Path

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect

from app.db import Base
from app.main import create_app
from tests.conftest import alembic_config, make_settings


def table_names(database_url: str) -> set[str]:
    engine = create_engine(database_url)
    try:
        return set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_migrations_match_models(database_url: str) -> None:
    """Поменяли модель и забыли миграцию — тест упадёт и покажет расхождение.

    database_url уже создан миграциями — на SQLite или, с TEST_DATABASE_URL, на PostgreSQL.
    """
    engine = create_engine(database_url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()

    assert diff == []


def test_downgrade_and_upgrade_again(tmp_path: Path) -> None:
    database_url = f"sqlite:///{tmp_path / 'm.db'}"
    config = alembic_config(database_url)

    command.upgrade(config, "head")
    command.downgrade(config, "base")
    assert table_names(database_url) == {"alembic_version"}

    command.upgrade(config, "head")
    assert {"tariffs", "payments"} <= table_names(database_url)


def test_app_refuses_to_start_without_migrations(tmp_path: Path) -> None:
    app = create_app(make_settings(f"sqlite:///{tmp_path / 'empty.db'}"))

    with pytest.raises(RuntimeError, match="alembic upgrade head"):
        with TestClient(app):
            pass
