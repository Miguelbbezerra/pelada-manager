from functools import lru_cache
from typing import Literal

from pydantic import SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEV_SECRET = "dev-only-nao-use-em-producao-troque-isso"  # noqa: S105 - recusado em prod


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: Literal["dev", "test", "prod"] = "dev"
    database_url: str = "postgresql+psycopg://pelada:pelada@localhost:5433/pelada"
    redis_url: str = "redis://localhost:6379/0"

    jwt_secret: SecretStr = SecretStr(DEV_SECRET)
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    login_attempts_per_minute: int = 5
    public_base_url: str = "http://localhost:8010"
    timezone: str = "America/Sao_Paulo"
    cors_origins: list[str] = []

    @model_validator(mode="after")
    def _check_secret(self) -> "Settings":
        secret = self.jwt_secret.get_secret_value()
        if self.environment == "prod" and (secret == DEV_SECRET or len(secret) < 32):
            raise ValueError("JWT_SECRET precisa ter pelo menos 32 caracteres em produção")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
