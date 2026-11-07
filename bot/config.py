import hashlib
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    bot_token: str
    # auto: webhook, если известен публичный адрес (Railway), иначе polling
    bot_mode: Literal["auto", "polling", "webhook"] = "auto"
    webhook_base_url: str = ""
    webhook_path: str = "/webhook"
    webhook_secret: str = ""
    railway_public_domain: str = ""
    port: int = 8080

    database_url: str = "sqlite+aiosqlite:///./dev.db"
    redis_url: str = ""
    encryption_key: str

    # Пустой ключ — ИИ-функции отключены, остальной бот работает
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-5-5"

    admin_ids: str = ""
    registration_mode: Literal["invite", "open"] = "invite"
    log_level: str = "INFO"

    @property
    def admin_id_set(self) -> set[int]:
        return {int(x) for x in self.admin_ids.replace(" ", "").split(",") if x.isdigit()}

    @property
    def webhook_url(self) -> str | None:
        if self.bot_mode == "polling":
            return None
        base = self.webhook_base_url
        if not base and self.railway_public_domain:
            base = f"https://{self.railway_public_domain}"
        if not base:
            if self.bot_mode == "webhook":
                raise ValueError("BOT_MODE=webhook требует WEBHOOK_BASE_URL или RAILWAY_PUBLIC_DOMAIN")
            return None
        return base.rstrip("/") + self.webhook_path

    @property
    def webhook_secret_value(self) -> str:
        # Telegram допускает в secret_token только A-Z, a-z, 0-9, _ и -
        return self.webhook_secret or hashlib.sha256(self.bot_token.encode()).hexdigest()[:32]


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
