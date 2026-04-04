"""Configuration settings for the Clinical Trial Site Recommender."""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass
class SupabaseConfig:
    """Supabase connection settings."""
    url: str = os.getenv("SUPABASE_URL", "")
    key: str = os.getenv("SUPABASE_KEY", "")  # anon/public key for client
    service_key: str = os.getenv("SUPABASE_SERVICE_KEY", "")  # service role key for admin ops


@dataclass
class ClinicalTrialsConfig:
    """ClinicalTrials.gov API settings."""
    base_url: str = "https://clinicaltrials.gov/api/v2"
    page_size: int = 1000  # Max allowed by API
    rate_limit_delay: float = 0.5  # Seconds between requests
    max_retries: int = 3
    retry_delay: float = 5.0


@dataclass
class Config:
    """Main configuration."""
    supabase: SupabaseConfig
    clinical_trials: ClinicalTrialsConfig
    
    # Data storage
    raw_data_dir: str = "data/raw"
    
    # Batch processing
    batch_size: int = 100  # Records to insert per batch


def get_config() -> Config:
    """Get application configuration."""
    return Config(
        supabase=SupabaseConfig(),
        clinical_trials=ClinicalTrialsConfig(),
    )
