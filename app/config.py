from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения: читаются из переменных окружения и файла .env."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./kvitto.db"
    # Секрет для подписи вебхуков банка. Значения по умолчанию нет намеренно: известный всем
    # секрет хуже отсутствующего. Не задан — все вебхуки отклоняются с 401.
    webhook_secret: str | None = None


settings = Settings()
