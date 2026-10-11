from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from app import models  # noqa: F401  — регистрирует таблицы в Base.metadata
from app.config import settings
from app.db import Base

config = context.config

if config.config_file_name is not None:
    # disable_existing_loggers=False: не глушить логгеры приложения, когда миграции
    # запускаются из кода (в тестах).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def get_database_url() -> str:
    # Тесты передают свою БД через config.attributes; иначе — DATABASE_URL приложения.
    return config.attributes.get("database_url") or settings.database_url


def run_migrations_offline() -> None:
    """Генерация SQL без подключения к БД: alembic upgrade head --sql."""
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(get_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
