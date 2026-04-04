"""Load clinical trial data from bulk downloaded JSON file from ClinicalTrials.gov."""

import json
import ijson
from pathlib import Path
from typing import Iterator

from src.ingestion.parser import parse_study
from src.ingestion.loader import DataLoader


def load_bulk_json_streaming(filepath: str) -> Iterator[dict]:
    """
    Stream studies from a large JSON file without loading entire file into memory.
    
    Supports two formats:
    1. Array format: [ {study1}, {study2}, ... ]
    2. Object format: { "studies": [ {study1}, {study2}, ... ] }
    
    Args:
        filepath: Path to the downloaded JSON file
        
    Yields:
        Individual study dictionaries
    """
    with open(filepath, 'rb') as f:
        # Check first character to determine format
        first_char = f.read(1)
        f.seek(0)
        
        if first_char == b'[':
            # Array format - direct array of studies
            parser = ijson.items(f, 'item')
        else:
            # Object format - studies nested under "studies" key
            parser = ijson.items(f, 'studies.item')
        
        for study in parser:
            yield study


def load_bulk_json_full(filepath: str) -> list[dict]:
    """
    Load entire JSON file into memory.
    
    Supports two formats:
    1. Array format: [ {study1}, {study2}, ... ]
    2. Object format: { "studies": [ {study1}, {study2}, ... ] }
    
    Args:
        filepath: Path to the downloaded JSON file
        
    Returns:
        List of study dictionaries
    """
    with open(filepath, 'r') as f:
        data = json.load(f)
    
    # Handle both array and object formats
    if isinstance(data, list):
        return data
    return data.get("studies", [])


async def load_bulk_file_to_database(
    filepath: str,
    batch_size: int = 100,
    streaming: bool = True,
    skip_count: int = 0,
) -> dict:
    """
    Load studies from a bulk downloaded JSON file into Supabase.
    
    Args:
        filepath: Path to the downloaded JSON file
        batch_size: Number of studies to process before committing
        streaming: Use streaming parser (lower memory) vs full load
        skip_count: Number of studies to skip (for resuming failed loads)
        
    Returns:
        Stats dictionary
    """
    loader = DataLoader()
    
    stats = {
        "total_processed": 0,
        "loaded_success": 0,
        "loaded_failure": 0,
        "skipped": skip_count,
    }
    
    # Get studies iterator
    if streaming:
        studies_iter = load_bulk_json_streaming(filepath)
    else:
        studies_iter = iter(load_bulk_json_full(filepath))
    
    # Skip if resuming
    for _ in range(skip_count):
        try:
            next(studies_iter)
        except StopIteration:
            break
    
    batch = []
    
    for study in studies_iter:
        batch.append(study)
        
        if len(batch) >= batch_size:
            success, failure = await loader.load_studies_batch(batch)
            stats["loaded_success"] += success
            stats["loaded_failure"] += failure
            stats["total_processed"] += len(batch)
            
            print(f"Processed {stats['total_processed']:,} | Success: {stats['loaded_success']:,} | Failed: {stats['loaded_failure']:,}")
            
            batch = []
    
    # Process remaining
    if batch:
        success, failure = await loader.load_studies_batch(batch)
        stats["loaded_success"] += success
        stats["loaded_failure"] += failure
        stats["total_processed"] += len(batch)
    
    print(f"\n{'='*50}")
    print(f"Bulk load complete!")
    print(f"  Total processed: {stats['total_processed']:,}")
    print(f"  Loaded successfully: {stats['loaded_success']:,}")
    print(f"  Failed: {stats['loaded_failure']:,}")
    print(f"{'='*50}")
    
    return stats


# CLI entry point
if __name__ == "__main__":
    import argparse
    import asyncio
    
    parser = argparse.ArgumentParser(description="Load bulk downloaded ClinicalTrials.gov JSON into Supabase")
    parser.add_argument(
        "filepath",
        type=str,
        help="Path to the downloaded JSON file"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=100,
        help="Number of studies per batch (default: 100)"
    )
    parser.add_argument(
        "--no-streaming",
        action="store_true",
        help="Load entire file into memory instead of streaming"
    )
    parser.add_argument(
        "--skip",
        type=int,
        default=0,
        help="Number of studies to skip (for resuming)"
    )
    
    args = parser.parse_args()
    
    asyncio.run(load_bulk_file_to_database(
        filepath=args.filepath,
        batch_size=args.batch_size,
        streaming=not args.no_streaming,
        skip_count=args.skip,
    ))
