from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mastodon_base_url: str = "https://mastodon.social"
    mastodon_access_token: SecretStr = SecretStr("")
    bluesky_service_url: str = "https://bsky.social"
    bluesky_identifier: str = ""
    bluesky_app_password: SecretStr = SecretStr("")
    devto_api_key: SecretStr = SecretStr("")
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""
    discord_webhook_url: SecretStr = SecretStr("")
    discord_guild_id: str = ""
    http_timeout_seconds: float = Field(default=10, gt=0, le=60)
    platform_timeout_seconds: float = Field(default=25, gt=0, le=120)
