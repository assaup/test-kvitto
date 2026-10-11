from fastapi import Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    """Бизнес-ошибка API с телом {"error": "<code>"}, например 409 invalid_transition."""

    def __init__(self, status_code: int, error: str) -> None:
        super().__init__(error)
        self.status_code = status_code
        self.error = error


async def api_error_handler(_request: Request, exc: Exception) -> JSONResponse:
    # Starlette типизирует обработчик через Exception; явная проверка вместо assert,
    # который отключается при запуске python -O.
    if not isinstance(exc, ApiError):
        raise exc
    return JSONResponse(status_code=exc.status_code, content={"error": exc.error})
