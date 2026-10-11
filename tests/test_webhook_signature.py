import hashlib
import hmac
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import WEBHOOK_SECRET, make_settings, payment_payload, signed_headers


@pytest.fixture
def payment_id(client: TestClient) -> str:
    return client.post("/payments", json=payment_payload()).json()["id"]


def webhook_body(payment_id: str, status: str = "succeeded") -> bytes:
    return json.dumps({"payment_id": payment_id, "status": status}).encode()


def assert_status(client: TestClient, payment_id: str, expected: str) -> None:
    assert client.get(f"/payments/{payment_id}").json()["status"] == expected


def test_valid_signature_is_accepted(client: TestClient, payment_id: str) -> None:
    body = webhook_body(payment_id)
    # Подпись считаем здесь независимо от app.signatures — по формуле из задания.
    signature = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()

    response = client.post(
        "/webhooks/bank",
        content=body,
        headers={"Content-Type": "application/json", "X-Signature": signature},
    )

    assert response.status_code == 200
    assert_status(client, payment_id, "succeeded")


def test_signature_in_uppercase_hex_is_accepted(client: TestClient, payment_id: str) -> None:
    body = webhook_body(payment_id)
    headers = signed_headers(body)
    headers["X-Signature"] = headers["X-Signature"].upper()

    response = client.post("/webhooks/bank", content=body, headers=headers)

    assert response.status_code == 200


@pytest.mark.parametrize(
    "signature",
    [
        None,  # заголовка нет
        "",
        "0" * 64,
        "not-a-signature",
        hmac.new(b"other-secret", b"", hashlib.sha256).hexdigest(),
    ],
)
def test_missing_or_wrong_signature_returns_401_and_keeps_status(
    client: TestClient, payment_id: str, signature: str | None
) -> None:
    headers = {"Content-Type": "application/json"}
    if signature is not None:
        headers["X-Signature"] = signature

    response = client.post("/webhooks/bank", content=webhook_body(payment_id), headers=headers)

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_signature"}
    assert_status(client, payment_id, "pending")


def test_signature_with_other_secret_returns_401(client: TestClient, payment_id: str) -> None:
    body = webhook_body(payment_id)

    response = client.post(
        "/webhooks/bank", content=body, headers=signed_headers(body, secret="other-secret")
    )

    assert response.status_code == 401
    assert_status(client, payment_id, "pending")


def test_tampered_body_returns_401(client: TestClient, payment_id: str) -> None:
    """Подпись от одного тела, а отправлено другое: злоумышленник подменил статус."""
    signed_body = webhook_body(payment_id, "succeeded")
    tampered_body = webhook_body(payment_id, "failed")

    response = client.post(
        "/webhooks/bank", content=tampered_body, headers=signed_headers(signed_body)
    )

    assert response.status_code == 401
    assert_status(client, payment_id, "pending")


def test_non_ascii_signature_returns_401_not_500(client: TestClient, payment_id: str) -> None:
    response = client.post(
        "/webhooks/bank",
        content=webhook_body(payment_id),
        headers={"Content-Type": "application/json", "X-Signature": "é".encode() * 32},
    )

    assert response.status_code == 401


def test_unsigned_invalid_body_returns_401_not_422(client: TestClient) -> None:
    """Без подписи не подсказываем 422, какие поля неверны: сначала проверяем подпись."""
    response = client.post(
        "/webhooks/bank",
        content=b'{"payment_id": "x", "status": "paid"}',
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 401


@pytest.mark.parametrize("secret", [None, ""])
def test_webhooks_are_rejected_when_secret_is_not_configured(
    tmp_path: Path, secret: str | None
) -> None:
    with TestClient(create_app(make_settings(tmp_path, webhook_secret=secret))) as client:
        payment_id = client.post("/payments", json=payment_payload()).json()["id"]
        body = webhook_body(payment_id)
        # Даже подпись, посчитанная с пустым ключом, не должна проходить.
        signature = hmac.new(b"", body, hashlib.sha256).hexdigest()

        response = client.post(
            "/webhooks/bank",
            content=body,
            headers={"Content-Type": "application/json", "X-Signature": signature},
        )

        assert response.status_code == 401
        assert_status(client, payment_id, "pending")
