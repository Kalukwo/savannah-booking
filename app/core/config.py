"""Application settings, read from the environment only."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


def _normalise_async_url(url: str) -> str:
    """Make a hosted Postgres URL usable by asyncpg.

    Hosting providers hand out postgres:// URLs carrying ?sslmode=require,
    which asyncpg does not understand. Rewrite the driver and translate
    sslmode into asyncpg's ssl parameter.
    """
    if url.startswith("postgres://"):
        url = "postgresql+asyncpg://" + url[len("postgres://"):]
    elif url.startswith("postgresql://"):
        url = "postgresql+asyncpg://" + url[len("postgresql://"):]

    if "sslmode=" in url:
        head, _, query = url.partition("?")
        parts = [p for p in query.split("&") if p]
        params = [p for p in parts if not p.startswith("sslmode=")]
        sslmode = next((p.split("=", 1)[1] for p in parts if p.startswith("sslmode=")), None)
        if sslmode in {"require", "verify-ca", "verify-full"}:
            params.append("ssl=require")
        url = head + ("?" + "&".join(params) if params else "")
    return url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/appointments"
    test_database_url: str | None = None

    @property
    def async_database_url(self) -> str:
        return _normalise_async_url(self.database_url)

    @property
    def async_test_database_url(self) -> str | None:
        if not self.test_database_url:
            return None
        return _normalise_async_url(self.test_database_url)


@lru_cache
def get_settings() -> Settings:
    return Settings()
