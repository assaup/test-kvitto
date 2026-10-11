from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlalchemy.orm import sessionmaker

from app.config import settings
from app.db import Base, make_engine


def create_app(database_url: str | None = None) -> FastAPI:
    """Фабрика приложения. В тестах вызывается с отдельной БД для каждого теста."""
    engine = make_engine(database_url or settings.database_url)
    session_factory = sessionmaker(engine, expire_on_commit=False)

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        Base.metadata.create_all(engine)
        yield
        engine.dispose()

    app = FastAPI(title="Kvitto Payments API", lifespan=lifespan)
    app.state.session_factory = session_factory
    return app


app = create_app()
