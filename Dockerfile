FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN addgroup --system app && adduser --system --ingroup app app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY alembic ./alembic
COPY alembic.ini .

RUN chown -R app:app /app
USER app

EXPOSE 8000

# Migrations are NOT in CMD.
#   Render: set a Pre-Deploy Command of `alembic upgrade head` in the
#           dashboard. It runs once per deploy, before instances boot, and a
#           failure aborts the deploy instead of boot-looping a bad container.
#   Local:  docker-compose runs `alembic upgrade head && uvicorn ...` as the
#           app service's command, so a fresh volume is migrated on start.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
