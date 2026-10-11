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


# Ожидаемые суммы посчитаны вручную по заданию (цена тарифа, KVITTO10 = −10%),
# а не взяты из кода — иначе тест сверял бы ответ сам с собой.
EXPECTED_PRICES = {
    # (tariff_id, promo_code): (amount, discount)
    (1, None): (990_000, 0),
    (1, "kvitto10"): (891_000, 99_000),
    (2, None): (1_990_000, 0),
    (2, "kvitto10"): (1_791_000, 199_000),
    (3, None): (2_990_000, 0),
    (3, "kvitto10"): (2_691_000, 299_000),
}


@pytest.mark.parametrize("months", [3, 6, 12])
@pytest.mark.parametrize(("tariff_id", "promo_code"), list(EXPECTED_PRICES))
def test_installment_schedule_sums_to_expected_amount(
    client: TestClient, tariff_id: int, promo_code: str | None, months: int
) -> None:
    expected_amount, expected_discount = EXPECTED_PRICES[(tariff_id, promo_code)]

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
    assert body["amount"] == expected_amount
    assert body["discount"] == expected_discount
    schedule = body["schedule"]
    assert len(schedule) == months
    assert sum(schedule) == expected_amount
    assert max(schedule) - min(schedule) <= 1
    assert schedule == sorted(schedule, reverse=True)  # лишние копейки — в первых платежах


@pytest.mark.parametrize(
    "email", ["Student@Example.COM", "  student@example.com  ", "\tStudent@example.com "]
)
def test_email_is_trimmed_and_lowercased(client: TestClient, email: str) -> None:
    response = client.post("/payments", json=payment_payload(email=email))

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
    error_field: str,
) -> None:
    response = client.post("/payments", json=payment_payload(**overrides))

    assert response.status_code == 422
    errors = response.json()["detail"]  # стандартный формат FastAPI
    assert any(error["loc"][:2] == ["body", error_field] for error in errors), errors
    assert count_payments() == 0


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"method": "installment"}, "installment_months is required for installment method"),
        ({"method": "installment", "installment_months": None}, "is required for installment"),
        ({"method": "card", "installment_months": 3}, "allowed only for installment method"),
        ({"method": "sbp", "installment_months": 12}, "allowed only for installment method"),
    ],
)
def test_installment_months_must_match_method(
    client: TestClient,
    count_payments: Callable[[], int],
    overrides: dict[str, Any],
    message: str,
) -> None:
    response = client.post("/payments", json=payment_payload(**overrides))

    assert response.status_code == 422
    errors = response.json()["detail"]
    # Ошибка уровня всей модели (зависит от двух полей), поэтому проверяем причину по тексту.
    assert any(message in error["msg"] for error in errors), errors
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
