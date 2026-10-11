FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Зависимости отдельным слоем: при изменении кода они не переустанавливаются.
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY alembic.ini .
COPY migrations ./migrations
COPY app ./app

# Не запускаем приложение от root.
RUN useradd --create-home --uid 1000 appuser
USER appuser

EXPOSE 8000

# Миграции — отдельный сервис migrate в docker-compose.yml, здесь только приложение.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
