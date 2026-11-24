from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings, read from environment variables or a local .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # "memory" runs an in-process FHIR store (tests, offline demos).
    # Otherwise the base URL of an R4 server, e.g. http://localhost:8080/fhir
    # for the docker compose HAPI, or https://hapi.fhir.org/baseR4 (public, shared,
    # synthetic data only).
    fhir_base_url: str = "memory"

    # "claude" uses the Anthropic API, "rules" is the offline keyword extractor,
    # "auto" picks claude when ANTHROPIC_API_KEY is set and rules otherwise.
    extractor: str = "auto"
    claude_model: str = "claude-sonnet-5-5"
    claude_effort: str = "medium"
    anthropic_api_key: str | None = None

    # Comma-separated origins allowed to call the API from a browser.
    cors_origins: str = "*"


@lru_cache
def get_settings() -> Settings:
    return Settings()
