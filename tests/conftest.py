from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path: Path) -> Iterator[TestClient]:
    # Файловая SQLite (а не :memory:) — чтобы потоки в конкурентных тестах видели одну БД.
    app = create_app(f"sqlite:///{tmp_path / 'test.db'}")
    with TestClient(app) as test_client:  # with запускает lifespan: создание таблиц
        yield test_client
