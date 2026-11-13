"""Application configuration, read from the environment.

The grader runs the container with ``--env-file .env`` and injects their own
values, so every setting below is environment-driven. Variable names match the
assignment's ``.env`` (OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL,
OPENAI_EMBEDDING_MODEL); matching is case-insensitive.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Repo root = parent of the ``app`` package. Used to resolve the corpus/cache
# dirs with absolute paths so the app works regardless of the current workdir.
ROOT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration."""

    # --- LLM access (OpenAI-compatible, e.g. a LiteLLM proxy) ---
    openai_api_key: str = ""
    # Accept the documented name AND the provided .env's typo (OPENAI_BASE_UR).
    openai_base_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices("openai_base_url", "openai_base_ur"),
    )
    openai_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    embedding_cache_version: str = Field(default="v1", min_length=1, max_length=100)
    embedding_dimensions: int | None = Field(default=None, ge=1, le=32768)

    # --- Paths ---
    corpus_dir: Path = ROOT_DIR / "corpus"
    cache_dir: Path = ROOT_DIR / ".cache"

    # --- Retrieval / agent tuning ---
    top_k: int = Field(default=5, ge=1, le=12)
    max_revisions: int = Field(default=2, ge=0, le=3)
    temperature: float | None = Field(default=None, ge=0, le=2)
    min_relevance: float = Field(default=0.18, ge=-1, le=1)
    request_timeout: float = Field(default=45.0, ge=1, le=120)
    answer_timeout: float = Field(default=180.0, ge=5, le=600)
    max_concurrent_requests: int = Field(default=2, ge=1, le=8)
    max_tool_calls: int = Field(default=24, ge=1, le=64)
    max_llm_calls: int = Field(default=16, ge=3, le=32)
    max_completion_tokens: int = Field(default=4096, ge=256, le=16384)
    max_evidence_chars: int = Field(default=60000, ge=4000, le=120000)
    max_context_chars: int = Field(default=100000, ge=16000, le=200000)

    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    @field_validator(
        "openai_api_key", "openai_base_url", "openai_model", "openai_embedding_model",
        mode="before",
    )
    @classmethod
    def _strip_quotes(cls, v: object) -> object:
        # docker --env-file keeps surrounding quotes literally; strip them defensively.
        if isinstance(v, str):
            return v.strip().strip('"').strip("'").strip()
        return v

    @field_validator("openai_model", "openai_embedding_model")
    @classmethod
    def _nonempty_model(cls, v: str) -> str:
        if not v:
            raise ValueError("model name cannot be blank")
        return v

    @field_validator("openai_base_url")
    @classmethod
    def _valid_endpoint(cls, v: str | None) -> str | None:
        if not v:
            return None
        from urllib.parse import urlparse
        parsed = urlparse(v)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("base URL must be an HTTP(S) endpoint without credentials, query or fragment")
        return v.rstrip("/")

    @property
    def has_llm(self) -> bool:
        """True when an API key is present (lets tests/health degrade gracefully)."""
        return bool(self.openai_api_key)


@lru_cache
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
