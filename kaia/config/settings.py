"""Pydantic settings with environment variable loading."""

from pydantic_settings import BaseSettings
from pydantic import Field, computed_field


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}

    # Telegram
    telegram_bot_token: str = Field(..., description="Telegram Bot API token")
    allowed_telegram_ids_str: str = Field(
        default="",
        alias="ALLOWED_TELEGRAM_IDS",
        description="Comma-separated Telegram user IDs (empty = allow all)",
    )

    @computed_field
    @property
    def allowed_telegram_ids(self) -> list[int]:
        raw = self.allowed_telegram_ids_str.strip()
        if not raw:
            return []
        return [int(x.strip()) for x in raw.split(",") if x.strip()]

    # AI — Claude (primary)
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    claude_model: str = Field("claude-sonnet-4-20250514", description="Claude model ID")
    claude_max_tokens: int = Field(1024, description="Max tokens per Claude response")

    # AI — Groq (fallback)
    groq_api_key: str = Field(default="", description="Groq API key for fallback")
    groq_model: str = Field("llama-3.3-70b-versatile", description="Groq model ID")

    # Supabase
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_key: str = Field(..., description="Supabase anon/service key")

    # Web search
    serpapi_key: str = Field(default="", description="SerpAPI key")

    # Weather / News (for briefings)
    openweather_api_key: str = Field(default="", description="OpenWeather API key")
    news_api_key: str = Field(default="", description="NewsAPI key")

    # Voice
    tts_voice: str = Field("en-US-AriaNeural", description="edge-tts voice name")
    voice_replies_enabled: bool = Field(False, description="Reply with voice by default")

    # Briefing & location
    default_location: str = Field("Manila, Philippines", description="Default weather location")
    briefing_time: str = Field("07:00", description="Default briefing time HH:MM")
    briefing_enabled: bool = Field(True, description="Enable daily scheduled briefing")

    # App behaviour
    default_timezone: str = Field("Asia/Manila", description="Default user timezone")
    default_currency: str = Field("PHP", description="Default currency code")
    intent_confidence_threshold: float = Field(
        0.6, description="Minimum confidence for intent routing"
    )
    max_conversation_history: int = Field(
        20, description="Max recent messages to include as context"
    )
    log_level: str = Field("INFO", description="Loguru log level")


def get_settings() -> Settings:
    """Create and return a cached Settings instance."""
    return Settings()  # type: ignore[call-arg]
