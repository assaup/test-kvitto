from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import make_settings

EXPECTED_TARIFFS = [
    {"id": 1, "title": "basic", "price": 990_000},
    {"id": 2, "title": "standard", "price": 1_990_000},
    {"id": 3, "title": "premium", "price": 2_990_000},
]


def test_list_tariffs_returns_seeded_tariffs_in_kopecks(client: TestClient) -> None:
    response = client.get("/tariffs")

    assert response.status_code == 200
    body = response.json()
    assert body == EXPECTED_TARIFFS
    # Цена приходит целым числом копеек, а не float/строкой.
    assert all(type(tariff["price"]) is int for tariff in body)


def test_tariffs_are_not_duplicated_on_restart(database_url: str) -> None:
    settings = make_settings(database_url)

    for _ in range(2):  # два запуска приложения на одной и той же БД
        with TestClient(create_app(settings)) as client:
            response = client.get("/tariffs")

    assert response.json() == EXPECTED_TARIFFS
