"""Подпись вебхуков банка: X-Signature = HMAC-SHA256(тело запроса, WEBHOOK_SECRET) в hex."""

import hashlib
import hmac


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def is_valid_signature(secret: str | None, body: bytes, signature: str | None) -> bool:
    if not secret or not signature:
        return False
    expected = sign(secret, body)
    # compare_digest сравнивает за одинаковое время, где бы ни было расхождение, — по времени
    # ответа нельзя подбирать подпись посимвольно. Сравниваем bytes, а не str: на строке
    # с не-ASCII символами compare_digest упал бы с TypeError (500 вместо 401).
    return hmac.compare_digest(expected.encode(), signature.lower().encode())
