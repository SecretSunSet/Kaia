"""Supabase client setup and connection management."""

from supabase import create_client, Client
from loguru import logger

from config.settings import get_settings

_client: Client | None = None


def get_supabase() -> Client:
    """Return a singleton Supabase client."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = create_client(settings.supabase_url, settings.supabase_key)
        logger.info("Supabase client initialised")
    return _client
