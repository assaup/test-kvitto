from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy import DateTime, Dialect, Engine, MetaData, TypeDecorator, create_engine
from sqlalchemy.orm import DeclarativeBase, Session


class Base(DeclarativeBase):
    # Предсказуемые имена индексов и ограничений: Alembic сможет найти, удалить или изменить
    # их в будущих миграциях.
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
    """Дата-время всегда в UTC и всегда с часовым поясом (в БД — timestamptz).

    PostgreSQL отдаёт время в часовом поясе сессии: при TimeZone=Europe/Moscow created_at
    пришёл бы с +03:00. Приводим к UTC, чтобы API отдавал время однозначно и одинаково.
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
        return None if value is None else value.astimezone(UTC)


def make_engine(database_url: str) -> Engine:
    # pool_pre_ping: проверить соединение перед выдачей из пула — после перезапуска
    # PostgreSQL первый запрос не упадёт на «мёртвом» соединении.
    return create_engine(database_url, pool_pre_ping=True)


def get_session(request: Request) -> Iterator[Session]:
    """Сессия БД на один запрос. Фабрика сессий лежит в app.state (см. create_app)."""
    with request.app.state.session_factory() as session:
        yield session


SessionDep = Annotated[Session, Depends(get_session)]
