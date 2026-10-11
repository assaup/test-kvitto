from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session

from app.models import Payment
from app.services import payments as payment_service
from tests.conftest import payment_payload


def test_same_idempotency_key_does_not_create_second_payment(
    client: TestClient, count_payments: Callable[[], int]
) -> None:
    headers = {"Idempotency-Key": "order-42"}

    first = client.post("/payments", json=payment_payload(), headers=headers)
    second = client.post("/payments", json=payment_payload(), headers=headers)

    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()  # тот же самый платёж, а не новый
    assert count_payments() == 1


def test_same_key_with_equivalent_body_is_a_replay(
    client: TestClient, count_payments: Callable[[], int]
) -> None:
    headers = {"Idempotency-Key": "order-42"}

    first = client.post("/payments", json=payment_payload(promo_code="KVITTO10"), headers=headers)
    # Промокод в другом регистре — это тот же самый запрос по смыслу.
    second = client.post("/payments", json=payment_payload(promo_code="kvitto10"), headers=headers)

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert count_payments() == 1


def test_same_key_with_email_in_other_case_is_a_replay(
    client: TestClient, count_payments: Callable[[], int]
) -> None:
    headers = {"Idempotency-Key": "order-42"}

    first = client.post(
        "/payments", json=payment_payload(email="student@example.com"), headers=headers
    )
    second = client.post(
        "/payments", json=payment_payload(email="Student@Example.com"), headers=headers
    )

    assert second.status_code == 200
    assert second.json()["id"] == first.json()["id"]
    assert count_payments() == 1


def test_huge_tariff_id_with_key_returns_422_not_500(
    client: TestClient, count_payments: Callable[[], int]
) -> None:
    response = client.post(
        "/payments",
        json=payment_payload(tariff_id=9_223_372_036_854_775_808),
        headers={"Idempotency-Key": "order-42"},
    )

    assert response.status_code == 422
    assert count_payments() == 0


def test_same_key_with_different_body_returns_409(
    client: TestClient, count_payments: Callable[[], int]
) -> None:
    headers = {"Idempotency-Key": "order-42"}
    first = client.post("/payments", json=payment_payload(tariff_id=1), headers=headers)

    response = client.post("/payments", json=payment_payload(tariff_id=3), headers=headers)

    assert response.status_code == 409
    assert response.json() == {"error": "idempotency_key_reused"}
    assert count_payments() == 1
    # Исходный платёж не изменился.
    assert client.get(f"/payments/{first.json()['id']}").json() == first.json()


def test_different_keys_create_different_payments(
    client: TestClient, count_payments: Callable[[], int]
) -> None:
    first = client.post("/payments", json=payment_payload(), headers={"Idempotency-Key": "a"})
    second = client.post("/payments", json=payment_payload(), headers={"Idempotency-Key": "b"})

    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]
    assert count_payments() == 2


def test_requests_without_key_are_not_deduplicated(
    client: TestClient, count_payments: Callable[[], int]
) -> None:
    client.post("/payments", json=payment_payload())
    client.post("/payments", json=payment_payload())

    assert count_payments() == 2


@pytest.mark.parametrize("key", ["", "x" * 256])
def test_invalid_idempotency_key_returns_422(
    client: TestClient, count_payments: Callable[[], int], key: str
) -> None:
    response = client.post("/payments", json=payment_payload(), headers={"Idempotency-Key": key})

    assert response.status_code == 422
    assert count_payments() == 0


def test_race_between_check_and_insert_returns_existing_payment(
    client: TestClient, count_payments: Callable[[], int], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Детерминированно воспроизводим гонку: первая проверка ключа «не видит» платёж,
    который уже создан параллельным запросом, и вставка упирается в UNIQUE."""
    headers = {"Idempotency-Key": "order-42"}
    first = client.post("/payments", json=payment_payload(), headers=headers)

    real_lookup = payment_service.find_by_idempotency_key
    calls = 0

    def lookup_missing_on_first_call(session: Session, key: str) -> Payment | None:
        nonlocal calls
        calls += 1
        return None if calls == 1 else real_lookup(session, key)

    monkeypatch.setattr(payment_service, "find_by_idempotency_key", lookup_missing_on_first_call)
    second = client.post("/payments", json=payment_payload(), headers=headers)

    assert calls == 2  # вторая проверка — после IntegrityError
    assert second.status_code == 200
    assert second.json() == first.json()
    assert count_payments() == 1


def test_concurrent_requests_with_same_key_create_one_payment(
    client: TestClient, count_payments: Callable[[], int]
) -> None:
    headers = {"Idempotency-Key": "order-42"}
    workers = 10
    start = Barrier(workers)  # все потоки отправляют запрос одновременно — так гонка вероятнее

    def send(_: int) -> Response:
        start.wait()
        return client.post("/payments", json=payment_payload(), headers=headers)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        responses = list(pool.map(send, range(workers)))

    statuses = sorted(response.status_code for response in responses)
    assert statuses == [200] * (workers - 1) + [201]
    assert len({response.json()["id"] for response in responses}) == 1
    assert count_payments() == 1
