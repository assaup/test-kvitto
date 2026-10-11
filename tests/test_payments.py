import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import payment_payload


def test_create_card_payment_without_promo(client: TestClient) -> None:
    response = client.post("/payments", json=payment_payload())

    assert response.status_code == 201
    body = response.json()
    uuid.UUID(body["id"])  # id — валидный UUID
    assert body["status"] == "pending"
    assert body["tariff_id"] == 2
    assert body["amount"] == 1_990_000
    assert body["discount"] == 0
    assert body["method"] == "card"
    assert body["installment_months"] is None
    assert body["schedule"] is None
    assert body["email"] == "student@example.com"
    created_at = datetime.fromisoformat(body["created_at"])
    assert created_at.utcoffset() is not None  # дата с часовым поясом
    assert abs(datetime.now(UTC) - created_at).total_seconds() < 60


@pytest.mark.parametrize("promo_code", ["KVITTO10", "kvitto10", " KvItTo10 "])
def test_create_payment_with_promo_code(client: TestClient, promo_code: str) -> None:
    response = client.post("/payments", json=payment_payload(promo_code=promo_code))

    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == 1_791_000
    assert body["discount"] == 199_000


def test_installment_example_from_spec(client: TestClient) -> None:
    response = client.post(
        "/payments", json=payment_payload(method="installment", installment_months=3)
    )

    assert response.status_code == 201
    body = response.json()
    assert body["amount"] == 1_990_000
    assert body["installment_months"] == 3
    assert body["schedule"] == [663_334, 663_333, 663_333]


@pytest.mark.parametrize("months", [3, 6, 12])
@pytest.mark.parametrize("promo_code", [None, "kvitto10"])
@pytest.mark.parametrize("tariff_id", [1, 2, 3])
def test_installment_schedule_sums_to_amount(
    client: TestClient, tariff_id: int, promo_code: str | None, months: int
) -> None:
    response = client.post(
        "/payments",
        json=payment_payload(
            tariff_id=tariff_id,
            method="installment",
            installment_months=months,
            promo_code=promo_code,
        ),
    )

    assert response.status_code == 201
    body = response.json()
    assert len(body["schedule"]) == months
    assert sum(body["schedule"]) == body["amount"]


def test_email_is_normalized_to_lowercase(client: TestClient) -> None:
    response = client.post("/payments", json=payment_payload(email="Student@Example.COM"))

    assert response.status_code == 201
    assert response.json()["email"] == "student@example.com"


def test_get_payment_returns_created_payment(client: TestClient) -> None:
    created = client.post(
        "/payments", json=payment_payload(method="installment", installment_months=6)
    ).json()

    response = client.get(f"/payments/{created['id']}")

    assert response.status_code == 200
    assert response.json() == created


@pytest.mark.parametrize("payment_id", [str(uuid.uuid4()), "999999", "not-a-uuid", "9" * 100])
def test_get_unknown_payment_returns_404(client: TestClient, payment_id: str) -> None:
    client.post("/payments", json=payment_payload())  # в БД есть другой платёж

    response = client.get(f"/payments/{payment_id}")

    assert response.status_code == 404
    assert response.json() == {"error": "payment_not_found"}


@pytest.mark.parametrize(
    ("overrides", "error_field"),
    [
        ({"method": "installment"}, None),  # рассрочка без installment_months
        ({"method": "card", "installment_months": 3}, None),  # срок без рассрочки
        ({"method": "installment", "installment_months": 4}, "installment_months"),
        ({"method": "installment", "installment_months": "3"}, "installment_months"),
        ({"method": "installment", "installment_months": 3.0}, "installment_months"),
        ({"method": "installment", "installment_months": True}, "installment_months"),
        ({"method": "cash"}, "method"),
        ({"promo_code": "KVITTO20"}, "promo_code"),
        ({"email": "not-an-email"}, "email"),
        ({"email": "Иван <ivan@example.com>"}, "email"),  # не переписываем адрес молча
        ({"tariff_id": 999}, "tariff_id"),
        ({"tariff_id": 2_147_483_647}, "tariff_id"),  # максимум INTEGER, но такого тарифа нет
        ({"tariff_id": 2_147_483_648}, "tariff_id"),
        ({"tariff_id": 9_223_372_036_854_775_808}, "tariff_id"),  # раньше — 500
        ({"tariff_id": 0}, "tariff_id"),
        ({"tariff_id": "2"}, "tariff_id"),
        ({"tariff_id": 2.0}, "tariff_id"),
        ({"tariff_id": True}, "tariff_id"),
        ({"amount": 1}, "amount"),  # сумму задаёт сервер, клиент её передать не может
    ],
)
def test_invalid_payment_returns_422_and_creates_nothing(
    client: TestClient,
    count_payments: Callable[[], int],
    overrides: dict[str, Any],
    error_field: str | None,
) -> None:
    response = client.post("/payments", json=payment_payload(**overrides))

    assert response.status_code == 422
    errors = response.json()["detail"]  # стандартный формат FastAPI
    if error_field is not None:
        assert any(error["loc"][:2] == ["body", error_field] for error in errors), errors
    assert count_payments() == 0


@pytest.mark.parametrize("field", ["tariff_id", "email", "method"])
def test_missing_required_field_returns_422(
    client: TestClient, count_payments: Callable[[], int], field: str
) -> None:
    payload = payment_payload()
    del payload[field]

    response = client.post("/payments", json=payload)

    assert response.status_code == 422
    assert count_payments() == 0
