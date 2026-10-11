from datetime import datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.conftest import payment_payload, send_webhook


@pytest.fixture
def payments(client: TestClient) -> dict[str, dict[str, Any]]:
    """Три платежа: два у anna (один оплачен), один у boris."""
    anna_card = client.post("/payments", json=payment_payload(email="anna@example.com")).json()
    boris = client.post(
        "/payments",
        json=payment_payload(email="boris@example.com", method="installment", installment_months=3),
    ).json()
    anna_sbp = client.post(
        "/payments", json=payment_payload(email="anna@example.com", method="sbp")
    ).json()
    assert send_webhook(client, anna_card["id"], "succeeded").status_code == 200
    anna_card = client.get(f"/payments/{anna_card['id']}").json()
    return {"anna_card": anna_card, "boris": boris, "anna_sbp": anna_sbp}


def ids(response_body: list[dict[str, Any]]) -> set[str]:
    return {payment["id"] for payment in response_body}


def test_list_without_filters_returns_all_payments_newest_first(
    client: TestClient, payments: dict[str, dict[str, Any]]
) -> None:
    response = client.get("/payments")

    assert response.status_code == 200
    body = response.json()
    assert ids(body) == {payment["id"] for payment in payments.values()}
    created = [datetime.fromisoformat(payment["created_at"]) for payment in body]
    assert created == sorted(created, reverse=True)
    # Элементы списка — полные платежи, ровно как в GET /payments/{id}.
    by_id = {payment["id"]: payment for payment in body}
    assert by_id[payments["anna_card"]["id"]] == payments["anna_card"]


@pytest.mark.parametrize("email", ["anna@example.com", "Anna@Example.COM", " anna@example.com "])
def test_filter_by_email_is_case_insensitive(
    client: TestClient, payments: dict[str, dict[str, Any]], email: str
) -> None:
    response = client.get("/payments", params={"email": email})

    assert response.status_code == 200
    assert ids(response.json()) == {payments["anna_card"]["id"], payments["anna_sbp"]["id"]}


@pytest.mark.parametrize(
    ("status", "expected"),
    [("succeeded", {"anna_card"}), ("pending", {"boris", "anna_sbp"}), ("refunded", set())],
)
def test_filter_by_status(
    client: TestClient, payments: dict[str, dict[str, Any]], status: str, expected: set[str]
) -> None:
    response = client.get("/payments", params={"status": status})

    assert response.status_code == 200
    assert ids(response.json()) == {payments[name]["id"] for name in expected}


def test_filters_are_combined(client: TestClient, payments: dict[str, dict[str, Any]]) -> None:
    response = client.get("/payments", params={"email": "anna@example.com", "status": "pending"})

    assert response.status_code == 200
    assert ids(response.json()) == {payments["anna_sbp"]["id"]}


@pytest.mark.parametrize("email", ["", "   "])
def test_empty_email_filter_means_no_filter(
    client: TestClient, payments: dict[str, dict[str, Any]], email: str
) -> None:
    response = client.get("/payments", params={"email": email})

    assert response.status_code == 200
    assert ids(response.json()) == {payment["id"] for payment in payments.values()}


def test_no_matches_returns_empty_list(
    client: TestClient, payments: dict[str, dict[str, Any]]
) -> None:
    response = client.get("/payments", params={"email": "nobody@example.com"})

    assert response.status_code == 200
    assert response.json() == []


def test_pagination_splits_list_without_gaps_or_duplicates(
    client: TestClient, payments: dict[str, dict[str, Any]]
) -> None:
    full = client.get("/payments").json()

    first_page = client.get("/payments", params={"limit": 2, "offset": 0}).json()
    second_page = client.get("/payments", params={"limit": 2, "offset": 2}).json()

    assert len(first_page) == 2
    assert len(second_page) == 1
    assert first_page + second_page == full


@pytest.mark.parametrize(
    "params",
    [
        {"status": "paid"},
        {"limit": 0},
        {"limit": 101},
        {"offset": -1},
        {"offset": 2**63},  # без верхней границы — 500 из БД
        {"limit": "ten"},
    ],
)
def test_invalid_query_params_return_422(client: TestClient, params: dict[str, Any]) -> None:
    response = client.get("/payments", params=params)

    assert response.status_code == 422
