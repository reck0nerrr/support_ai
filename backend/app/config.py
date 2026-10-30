from functools import lru_cache
from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://copilot:copilot@localhost:5432/copilot"
    environment: str = "development"
    public_origin: str = "http://localhost:5173"
    cookie_secure: bool = False
    session_hours: int = 12
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    ai_provider: str = "offline"
    openai_api_key: str = ""
    openai_model: str = ""
    demo_enabled: bool = False

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
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
