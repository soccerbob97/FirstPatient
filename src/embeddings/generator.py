"""Generate embeddings using OpenAI text-embedding-3-small."""

import os
from typing import List, Optional
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536

# Simple in-memory cache for embeddings (exact match)
# Using a dict with LRU-like behavior via lru_cache
_embedding_cache: dict[str, List[float]] = {}
_CACHE_MAX_SIZE = 1000  # Limit cache to 1000 entries


def _normalize_text(text: str) -> str:
    """Normalize text for cache key (lowercase, strip whitespace)."""
    return text.lower().strip()


def get_embedding(text: str, use_cache: bool = True) -> Optional[List[float]]:
    """
    Generate embedding for a single text with optional caching.
    
    Args:
        text: Text to embed
        use_cache: Whether to use the embedding cache (default True)
        
    Returns:
        List of floats (1536 dimensions)
    """
    if not text or not text.strip():
        return None
    
    # Normalize for cache lookup
    cache_key = _normalize_text(text)
    
    # Check cache first
    if use_cache and cache_key in _embedding_cache:
        return _embedding_cache[cache_key]
    
    # Truncate to ~8000 tokens (~32000 chars) to stay within limits
    text = text[:32000]
    
    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    
    embedding = response.data[0].embedding
    
    # Store in cache (with simple size limit)
    if use_cache:
        if len(_embedding_cache) >= _CACHE_MAX_SIZE:
            # Remove oldest entry (first key) - simple eviction
            oldest_key = next(iter(_embedding_cache))
            del _embedding_cache[oldest_key]
        _embedding_cache[cache_key] = embedding
    
    return embedding


def get_cache_stats() -> dict:
    """Return cache statistics for monitoring."""
    return {
        "size": len(_embedding_cache),
        "max_size": _CACHE_MAX_SIZE,
    }


def clear_cache() -> None:
    """Clear the embedding cache."""
    _embedding_cache.clear()


def get_embeddings_batch(texts: List[str], batch_size: int = 100) -> List[List[float]]:
    """
    Generate embeddings for multiple texts in batches.
    
    Args:
        texts: List of texts to embed
        batch_size: Number of texts per API call
        
    Returns:
        List of embeddings (same order as input)
    """
    all_embeddings = []
    
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        
        # Filter out empty texts, track indices
        valid_texts = []
        valid_indices = []
        for j, text in enumerate(batch):
            if text and text.strip():
                valid_texts.append(text[:32000])  # Truncate
                valid_indices.append(j)
        
        # Get embeddings for valid texts
        if valid_texts:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL,
                input=valid_texts,
                dimensions=EMBEDDING_DIMENSIONS,
            )
            
            # Map back to original indices
            batch_embeddings = [None] * len(batch)
            for idx, embedding_data in zip(valid_indices, response.data):
                batch_embeddings[idx] = embedding_data.embedding
            
            all_embeddings.extend(batch_embeddings)
        else:
            all_embeddings.extend([None] * len(batch))
    
    return all_embeddings


def build_trial_text_for_embedding(trial: dict) -> str:
    """
    Build text representation of a trial for embedding.
    
    Args:
        trial: Trial record from database
        
    Returns:
        Text suitable for embedding
    """
    parts = []
    
    if trial.get("brief_title"):
        parts.append(f"Title: {trial['brief_title']}")
    
    if trial.get("brief_summary"):
        parts.append(f"Summary: {trial['brief_summary']}")
    
    if trial.get("conditions"):
        conditions = trial["conditions"]
        if isinstance(conditions, list):
            parts.append(f"Conditions: {', '.join(conditions)}")
        else:
            parts.append(f"Conditions: {conditions}")
    
    if trial.get("phase"):
        parts.append(f"Phase: {trial['phase']}")
    
    if trial.get("study_type"):
        parts.append(f"Study Type: {trial['study_type']}")
    
    return "\n".join(parts)


def build_investigator_expertise_profile(
    investigator: dict,
    trials: List[dict],
) -> str:
    """
    Build expertise profile text for an investigator based on their trial history.
    
    Args:
        investigator: Investigator record
        trials: List of trials they've worked on
        
    Returns:
        Expertise profile text for embedding
    """
    if not trials:
        return None
    
    # Collect all conditions, phases, sponsors
    all_conditions = set()
    all_phases = set()
    all_sponsors = set()
    
    for trial in trials:
        if trial.get("conditions"):
            conditions = trial["conditions"]
            if isinstance(conditions, list):
                all_conditions.update(conditions)
            else:
                all_conditions.add(conditions)
        
        if trial.get("phase"):
            all_phases.add(trial["phase"])
        
        if trial.get("lead_sponsor_class"):
            all_sponsors.add(trial["lead_sponsor_class"])
    
    # Build profile
    parts = [
        f"Principal Investigator: {investigator.get('full_name', 'Unknown')}",
    ]
    
    if investigator.get("affiliation"):
        parts.append(f"Affiliation: {investigator['affiliation']}")
    
    parts.append(f"Total trials: {len(trials)}")
    
    if all_conditions:
        parts.append(f"Therapeutic areas: {', '.join(sorted(all_conditions)[:20])}")  # Limit to top 20
    
    if all_phases:
        parts.append(f"Phase experience: {', '.join(sorted(all_phases))}")
    
    if all_sponsors:
        parts.append(f"Sponsor types: {', '.join(sorted(all_sponsors))}")
    
    return "\n".join(parts)
