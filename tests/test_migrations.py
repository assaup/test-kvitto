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
    """Поменяли модель и забыли миграцию — тест упадёт и покажет расхождение."""
    engine = create_engine(database_url)
    with engine.connect() as connection:
        diff = compare_metadata(MigrationContext.configure(connection), Base.metadata)
    engine.dispose()

    assert diff == []


# Два теста ниже откатывают схему тестовой базы, поэтому в finally всегда возвращают её
# к head — иначе следующие тесты остались бы без таблиц.


def test_downgrade_and_upgrade_again(database_url: str) -> None:
    config = alembic_config(database_url)

    try:
        command.downgrade(config, "base")
        assert table_names(database_url) == {"alembic_version"}
    finally:
        command.upgrade(config, "head")

    assert {"tariffs", "payments"} <= table_names(database_url)


def test_app_refuses_to_start_without_migrations(database_url: str) -> None:
    config = alembic_config(database_url)
    command.downgrade(config, "base")

    try:
        with pytest.raises(RuntimeError, match="alembic upgrade head"):
            with TestClient(create_app(make_settings(database_url))):
                pass
    finally:
        command.upgrade(config, "head")
