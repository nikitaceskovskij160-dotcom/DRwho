FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN useradd --create-home app && chown -R app /app
USER app

# Миграции при старте: Railway не применяет preDeployCommand из railway.json, реплика одна
CMD ["sh", "-c", "alembic upgrade head && python -m bot"]
