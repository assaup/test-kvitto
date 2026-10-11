from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения: читаются из переменных окружения и файла .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # По умолчанию — PostgreSQL из docker-compose.yml (порт 5433 на хосте).
    database_url: str = "postgresql+psycopg://kvitto:kvitto@localhost:5433/kvitto"
    # Секрет для подписи вебхуков банка. Значения по умолчанию нет намеренно: известный всем
    # секрет хуже отсутствующего. Не задан — все вебхуки отклоняются с 401.
    webhook_secret: str | None = None


settings = Settings()
