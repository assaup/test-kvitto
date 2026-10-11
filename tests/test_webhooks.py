import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from itertools import product
from threading import Barrier
from typing import Any

import pytest
from fastapi.testclient import TestClient
from httpx import Response

from tests.conftest import payment_payload

STATUSES = ["pending", "succeeded", "failed", "refunded"]

# Таблица из задания — намеренно не импортируем ALLOWED_TRANSITIONS из кода,
# иначе тест сверял бы код сам с собой.
ALLOWED_BY_SPEC = {("pending", "succeeded"), ("pending", "failed"), ("succeeded", "refunded")}

# Как довести новый (pending) платёж до нужного статуса разрешёнными вебхуками.
PATH_TO_STATUS = {
    "pending": [],
    "succeeded": ["succeeded"],
    "failed": ["failed"],
    "refunded": ["succeeded", "refunded"],
}


def send_webhook(client: TestClient, payment_id: str | int, status: str) -> Response:
    return client.post("/webhooks/bank", json={"payment_id": payment_id, "status": status})


@pytest.fixture
def create_payment_in(client: TestClient) -> Callable[[str], str]:
    """Создаёт платёж и переводит его в нужный статус. Возвращает id платежа."""

    def _create(status: str) -> str:
        payment_id = client.post("/payments", json=payment_payload()).json()["id"]
        for step in PATH_TO_STATUS[status]:
            assert send_webhook(client, payment_id, step).status_code == 200
        assert client.get(f"/payments/{payment_id}").json()["status"] == status
        return payment_id

    return _create


@pytest.mark.parametrize(("current", "target"), sorted(ALLOWED_BY_SPEC))
def test_allowed_transition_changes_status(
    client: TestClient, create_payment_in: Callable[[str], str], current: str, target: str
) -> None:
    payment_id = create_payment_in(current)

    response = send_webhook(client, payment_id, target)

    assert response.status_code == 200
    assert response.json() == {"result": "ok"}
    assert client.get(f"/payments/{payment_id}").json()["status"] == target


@pytest.mark.parametrize(
    ("current", "target"),
    [pair for pair in product(STATUSES, STATUSES) if pair not in ALLOWED_BY_SPEC],
)
def test_forbidden_transition_returns_409_and_keeps_status(
    client: TestClient, create_payment_in: Callable[[str], str], current: str, target: str
) -> None:
    payment_id = create_payment_in(current)
    before = client.get(f"/payments/{payment_id}").json()

    response = send_webhook(client, payment_id, target)

    assert response.status_code == 409
    assert response.json() == {"error": "invalid_transition"}
    assert client.get(f"/payments/{payment_id}").json() == before  # платёж не изменился


@pytest.mark.parametrize("payment_id", [str(uuid.uuid4()), "999999", 999999, "not-a-uuid", 2**63])
def test_webhook_for_unknown_payment_returns_404_and_changes_nothing(
    client: TestClient, create_payment_in: Callable[[str], str], payment_id: str | int
) -> None:
    existing_id = create_payment_in("pending")

    response = send_webhook(client, payment_id, "succeeded")

    assert response.status_code == 404
    assert response.json() == {"error": "payment_not_found"}
    assert client.get(f"/payments/{existing_id}").json()["status"] == "pending"


@pytest.mark.parametrize(
    "body",
    [
        {"status": "succeeded"},
        {"payment_id": None, "status": "succeeded"},
        {"payment_id": True, "status": "succeeded"},  # не превращается в 1
        {"payment_id": 1.5, "status": "succeeded"},
        {"payment_id": {"id": "PAYMENT_ID"}, "status": "succeeded"},
        {"payment_id": "PAYMENT_ID", "status": "paid"},
        {"payment_id": "PAYMENT_ID"},
    ],
)
def test_invalid_webhook_body_returns_422_and_keeps_status(
    client: TestClient, create_payment_in: Callable[[str], str], body: dict[str, Any]
) -> None:
    payment_id = create_payment_in("pending")
    if body.get("payment_id") == "PAYMENT_ID":
        body = {**body, "payment_id": payment_id}

    response = client.post("/webhooks/bank", json=body)

    assert response.status_code == 422
    assert client.get(f"/payments/{payment_id}").json()["status"] == "pending"


def test_concurrent_conflicting_webhooks_apply_exactly_one(
    client: TestClient, create_payment_in: Callable[[str], str]
) -> None:
    """Банк одновременно шлёт succeeded и failed для одного pending-платежа:
    применяется ровно один, остальные получают 409."""
    payment_id = create_payment_in("pending")
    targets = ["succeeded", "failed"] * 5
    start = Barrier(len(targets))

    def send(target: str) -> tuple[str, Response]:
        start.wait()
        return target, send_webhook(client, payment_id, target)

    with ThreadPoolExecutor(max_workers=len(targets)) as pool:
        results = list(pool.map(send, targets))

    winners = [target for target, response in results if response.status_code == 200]
    losers = [response for _, response in results if response.status_code != 200]
    assert len(winners) == 1
    assert all(response.status_code == 409 for response in losers)
    assert client.get(f"/payments/{payment_id}").json()["status"] == winners[0]
