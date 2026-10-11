from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import (
    DateTime,
    Dialect,
    Engine,
    MetaData,
    TypeDecorator,
    create_engine,
    event,
)
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    # Предсказуемые имена индексов и ограничений: Alembic сможет удалить или изменить их
    # в будущих миграциях (на SQLite через batch-режим без имени ограничение не найти).
    metadata = MetaData(
        naming_convention={
            "ix": "ix_%(column_0_label)s",
            "uq": "uq_%(table_name)s_%(column_0_name)s",
            "ck": "ck_%(table_name)s_%(constraint_name)s",
            "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
            "pk": "pk_%(table_name)s",
        }
    )


class UTCDateTime(TypeDecorator[datetime]):
    """Дата-время всегда в UTC и всегда с часовым поясом.

    SQLite не хранит часовой пояс и возвращает «наивный» datetime — добавляем UTC обратно,
    чтобы в API created_at всегда отдавался однозначно (с +00:00).
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("Naive datetime is not allowed, use timezone-aware UTC")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


def make_engine(database_url: str) -> Engine:
    is_sqlite = database_url.startswith("sqlite")
    # FastAPI выполняет sync-эндпоинты в пуле потоков, поэтому одно SQLite-соединение
    # может использоваться из разных потоков. timeout — сколько ждать снятия блокировки БД.
    connect_args = {"check_same_thread": False, "timeout": 30} if is_sqlite else {}
    engine = create_engine(database_url, connect_args=connect_args)

    if is_sqlite:
        # SQLite по умолчанию не проверяет внешние ключи — включаем явно.
        @event.listens_for(engine, "connect")
        def _enable_foreign_keys(dbapi_connection, _connection_record) -> None:
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()

    return engine


def get_session(request: Request) -> Iterator[Session]:
    """Сессия БД на один запрос. Фабрика сессий лежит в app.state (см. create_app)."""
    with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
