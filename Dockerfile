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

# Documentation only: Render supplies $PORT at runtime and ignores EXPOSE.
EXPOSE 8000

# Migrations run here and nowhere else - Render's Pre-Deploy Command stays empty.
# uvicorn takes over via exec so it receives SIGTERM from the platform directly.
# ${PORT:-8000} must stay inside sh -c: JSON-array CMD does not expand vars.
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
