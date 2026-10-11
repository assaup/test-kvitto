import logging
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy import inspect
from sqlalchemy.orm import sessionmaker

from app import models
from app.config import Settings, settings
from app.db import make_engine
from app.errors import ApiError, api_error_handler
from app.routers import payments, tariffs, webhooks
from app.seed import seed_tariffs

logger = logging.getLogger(__name__)


def create_app(app_settings: Settings | None = None) -> FastAPI:
    """Фабрика приложения. Тесты передают свои настройки: отдельную БД и секрет вебхуков."""
    app_settings = app_settings or settings
    engine = make_engine(app_settings.database_url)
    session_factory = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
        if not app_settings.webhook_secret:
            logger.warning("WEBHOOK_SECRET не задан: все вебхуки банка будут отклоняться с 401")
        # Схему создают только миграции Alembic — отдельным шагом, а не при старте приложения:
        # иначе несколько воркеров запускали бы миграции одновременно.
        if not inspect(engine).has_table(models.Tariff.__tablename__):
            raise RuntimeError("База не инициализирована: выполните `alembic upgrade head`")
        with session_factory() as session:
            seed_tariffs(session)
        yield
        engine.dispose()

    app = FastAPI(title="Kvitto Payments API", lifespan=lifespan)
    app.state.settings = app_settings
    app.state.session_factory = session_factory
    app.add_exception_handler(ApiError, api_error_handler)
    app.include_router(tariffs.router)
    app.include_router(payments.router)
    app.include_router(webhooks.router)
    return app


app = create_app()
