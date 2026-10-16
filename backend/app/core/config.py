"""Configuração da aplicação, lida de variáveis de ambiente (e de um `.env` opcional)."""

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Aplicação
    app_env: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    cors_origins: Annotated[list[str], NoDecode] = Field(
        default_factory=lambda: ["http://localhost:3000"]
    )

    # Sessão de login (cookie httpOnly com um token aleatório)
    session_cookie_name: str = "icgrifo_session"
    session_days: int = 30
    # None = só em produção. Desligue apenas em ambientes sem HTTPS.
    session_cookie_secure: bool | None = None
    # "none" quando front e API ficarem em sites diferentes (exige HTTPS).
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # Banco de dados (Postgres com pgvector — Supabase em produção)
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:54329/icgrifo"
    # Ative quando usar o pooler do Supabase em modo transação (porta 6543),
    # que não suporta prepared statements.
    database_pgbouncer: bool = False
    database_pool_size: int = 5

    # Armazenamento de arquivos
    storage_backend: Literal["supabase", "local"] = "local"
    supabase_url: str = ""
    supabase_service_key: SecretStr = SecretStr("")
    supabase_bucket: str = "documents"
    local_storage_dir: Path = Path("./data/storage")

    # Limites
    max_upload_mb: int = 50
    llm_rate_limit_per_minute: int = 20

    # LLM
    anthropic_api_key: SecretStr = SecretStr("")
    llm_model: str = "claude-sonnet-5-5"
    llm_max_concurrency: int = 4
    llm_chunk_chars: int = 12000
    llm_chunk_overlap: int = 1500

    # Embeddings
    embedding_provider: Literal["local", "api"] = "local"
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_dim: int = 384
    embedding_api_url: str = ""
    embedding_api_key: SecretStr = SecretStr("")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [o.strip() for o in value.split(",") if o.strip()]
        return value

    @field_validator("database_url", mode="after")
    @classmethod
    def _use_asyncpg(cls, value: str) -> str:
        # Aceita a URL no formato copiado do Supabase (postgresql:// ou postgres://).
        for prefix in ("postgresql://", "postgres://"):
            if value.startswith(prefix):
                return "postgresql+asyncpg://" + value[len(prefix) :]
        return value

    @property
    def cookie_secure(self) -> bool:
        if self.session_cookie_secure is not None:
            return self.session_cookie_secure
        return self.app_env == "production"

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024


@lru_cache
def get_settings() -> Settings:
    return Settings()
