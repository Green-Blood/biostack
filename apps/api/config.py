from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    database_url: str = f"sqlite:///{ROOT / 'biostack.db'}"
    api_secret_key: str = "dev-secret-change-me"
    data_dir: Path = ROOT / "data"
    gemini_api_key: str = ""
    gemini_model: str = ""
    ai_provider: str = "gemini"  # "gemini" | "openai_compat"
    openai_base_url: str = ""
    openai_api_key: str = ""
    openai_model: str = ""
    app_env: str = ""
    biostack_fake_ai: bool = False
    enable_scheduler: bool = False
    telegram_bot_token: str = ""
    telegram_owner_id: str = ""
    biostack_api_url: str = "http://127.0.0.1:8000"
    bot_lang: str = "en"

    @model_validator(mode="after")
    def _fake_ai_only_in_test(self) -> "Settings":
        if self.biostack_fake_ai and self.app_env != "test":
            raise ValueError("BIOSTACK_FAKE_AI=1 is allowed only together with APP_ENV=test")
        return self


settings = Settings()
