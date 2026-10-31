from functools import lru_cache
from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        env_ignore_empty=True,
        hide_input_in_errors=True,
    )
    database_url: str = "postgresql+psycopg://copilot:copilot@localhost:5432/copilot"
    environment: str = "development"
    public_origin: str = "http://localhost:8080"
    cookie_secure: bool = False
    session_hours: int = 12
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    ai_provider: str = "offline"
    openai_api_key: str = ""
    openai_model: str = ""
    demo_enabled: bool = False
    auto_reply_enabled: bool = True
    triage_api_key: str = ""
    openai_reasoning_effort: str = ""
    model_input_usd_per_million: float | None = None
    model_cached_input_usd_per_million: float | None = None
    model_output_usd_per_million: float | None = None
    model_cache_write_usd_per_million: float | None = None
    predict_rpm: float = Field(default=12, ge=0, le=600)
    handout_dir: str = "private/handout"
    rag_top_k: int = Field(default=8, ge=2, le=16)
    rag_max_chars: int = Field(default=10000, ge=2000, le=24000)
    llm_retry_max_wait_seconds: float = Field(default=60, ge=0, le=3600)

    @model_validator(mode="after")
    def validate_configuration(self):
        if self.ai_provider not in {"offline", "openai"}:
            raise ValueError("AI_PROVIDER must be offline or openai")
        if self.ai_provider == "openai" and not (
            self.openai_api_key and self.openai_model
        ):
            raise ValueError("Set OPENAI_API_KEY and OPENAI_MODEL for OpenAI")
        if self.environment == "production":
            if not self.cookie_secure or not self.public_origin.startswith("https://"):
                raise ValueError("Production requires HTTPS and COOKIE_SECURE=true")
            if self.demo_enabled:
                raise ValueError("Disable demo in production")
            if not self.triage_api_key:
                raise ValueError("Set TRIAGE_API_KEY in production")
        rates = [
            self.model_input_usd_per_million,
            self.model_output_usd_per_million,
            self.model_cached_input_usd_per_million,
            self.model_cache_write_usd_per_million,
        ]
        if any(v is not None and v < 0 for v in rates):
            raise ValueError("Token prices cannot be negative")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
