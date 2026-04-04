"""Supabase client wrapper for database operations."""

from supabase import create_client, Client
from src.config import get_config


_client: Client | None = None


def get_supabase_client() -> Client:
    """Get or create Supabase client singleton."""
    global _client
    if _client is None:
        config = get_config()
        _client = create_client(config.supabase.url, config.supabase.service_key)
    return _client


def get_supabase_admin_client() -> Client:
    """Get Supabase client with service role key for admin operations."""
    config = get_config()
    return create_client(config.supabase.url, config.supabase.service_key)
