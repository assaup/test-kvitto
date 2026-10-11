from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app import models  # noqa: F401  — регистрирует таблицы в Base.metadata
from app.config import settings
from app.db import Base, make_engine
from app.errors import ApiError, api_error_handler
from app.routers import payments, tariffs, webhooks
from app.seed import seed_tariffs


def create_app(database_url: str | None = None) -> FastAPI:
    """Фабрика приложения. В тестах вызывается с отдельной БД для каждого теста."""
    engine = make_engine(database_url or settings.database_url)
    session_factory = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        Base.metadata.create_all(engine)
        with session_factory() as session:
            seed_tariffs(session)
        yield
        engine.dispose()

    app = FastAPI(title="Kvitto Payments API", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(tariffs.router)
    app.include_router(payments.router)
    app.include_router(webhooks.router)
    return app


app = create_app()
