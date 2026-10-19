"""Storage for Idempotency-Key responses."""
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.idempotency import IdempotencyKey


class IdempotencyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def claim(self, key: str, request_hash: str, now: datetime) -> tuple[bool, dict | None]:
        """Insert the key if free; return (claimed, existing_row).

        WHY ON CONFLICT DO NOTHING: a concurrent request with the same key
        blocks on the unique insert until the first commits, then sees the
        stored response instead of booking twice.
        """
        await self.purge_expired(now)
        stmt = (
            pg_insert(IdempotencyKey)
            .values(
                key=key,
                request_hash=request_hash,
                response_status=200,
                response_body={},
                created_at=now,
            )
            .on_conflict_do_nothing(index_elements=[IdempotencyKey.key])
            .returning(IdempotencyKey.key)
        )
        inserted = (await self.session.execute(stmt)).scalar_one_or_none()
        if inserted is not None:
            return True, None

        existing = (
            await self.session.execute(
                select(IdempotencyKey).where(IdempotencyKey.key == key)
            )
        ).scalar_one()
        return False, {
            "hash": existing.request_hash,
            "status": existing.response_status,
            "body": existing.response_body,
        }

    async def store(self, key: str, status: int, body: dict) -> None:
        row = (
            await self.session.execute(
                select(IdempotencyKey).where(IdempotencyKey.key == key)
            )
        ).scalar_one()
        row.response_status = status
        row.response_body = body

    async def purge_expired(self, now: datetime) -> None:
        await self.session.execute(
            delete(IdempotencyKey).where(IdempotencyKey.created_at < now - __import__("datetime").timedelta(hours=24))
        )
