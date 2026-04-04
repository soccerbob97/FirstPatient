"""Bulk download orchestrator for ClinicalTrials.gov data."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path

from src.config import get_config
from src.ingestion.ct_client import ClinicalTrialsClient
from src.ingestion.loader import DataLoader


async def bulk_download_to_files(
    output_dir: str = "data/raw",
    query: str | None = None,
) -> int:
    """
    Download all studies from CT.gov and save to JSON files.
    
    This is useful for:
    1. Creating a local backup before loading to DB
    2. Resuming failed loads without re-downloading
    
    Args:
        output_dir: Directory to save JSON files
        query: Optional search query to filter studies
        
    Returns:
        Total number of studies downloaded
    """
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    client = ClinicalTrialsClient()
    total_downloaded = 0
    batch_num = 0
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    async for studies in client.fetch_all_studies(query=query):
        batch_num += 1
        filename = f"{output_dir}/studies_batch_{timestamp}_{batch_num:05d}.json"
        
        with open(filename, 'w') as f:
            json.dump(studies, f)
        
        total_downloaded += len(studies)
        print(f"Saved batch {batch_num} ({len(studies)} studies) to {filename}")
    
    print(f"\nDownload complete! Total: {total_downloaded:,} studies in {batch_num} files")
    return total_downloaded


async def bulk_download_to_database(
    query: str | None = None,
    save_raw: bool = True,
) -> dict:
    """
    Download all studies and load directly into Supabase.
    
    Args:
        query: Optional search query to filter studies
        save_raw: Also save raw JSON files as backup
        
    Returns:
        Stats dict with counts
    """
    config = get_config()
    
    if save_raw:
        Path(config.raw_data_dir).mkdir(parents=True, exist_ok=True)
    
    client = ClinicalTrialsClient()
    loader = DataLoader()
    
    stats = {
        "total_fetched": 0,
        "loaded_success": 0,
        "loaded_failure": 0,
        "batches": 0,
    }
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    async for studies in client.fetch_all_studies(query=query):
        stats["batches"] += 1
        stats["total_fetched"] += len(studies)
        
        # Optionally save raw JSON
        if save_raw:
            filename = f"{config.raw_data_dir}/batch_{timestamp}_{stats['batches']:05d}.json"
            with open(filename, 'w') as f:
                json.dump(studies, f)
        
        # Load into database
        success, failure = await loader.load_studies_batch(studies)
        stats["loaded_success"] += success
        stats["loaded_failure"] += failure
        
        print(f"Batch {stats['batches']}: {success} loaded, {failure} failed")
    
    print(f"\n{'='*50}")
    print(f"Bulk download complete!")
    print(f"  Total fetched: {stats['total_fetched']:,}")
    print(f"  Loaded successfully: {stats['loaded_success']:,}")
    print(f"  Failed: {stats['loaded_failure']:,}")
    print(f"{'='*50}")
    
    return stats


async def load_from_files(input_dir: str = "data/raw") -> dict:
    """
    Load studies from previously downloaded JSON files into database.
    
    Useful for resuming after a failed load.
    
    Args:
        input_dir: Directory containing JSON batch files
        
    Returns:
        Stats dict
    """
    loader = DataLoader()
    
    stats = {
        "files_processed": 0,
        "total_studies": 0,
        "loaded_success": 0,
        "loaded_failure": 0,
    }
    
    json_files = sorted(Path(input_dir).glob("*.json"))
    print(f"Found {len(json_files)} JSON files to process")
    
    for filepath in json_files:
        stats["files_processed"] += 1
        
        with open(filepath, 'r') as f:
            studies = json.load(f)
        
        stats["total_studies"] += len(studies)
        
        success, failure = await loader.load_studies_batch(studies)
        stats["loaded_success"] += success
        stats["loaded_failure"] += failure
        
        print(f"File {stats['files_processed']}/{len(json_files)}: {filepath.name} - {success} loaded, {failure} failed")
    
    print(f"\n{'='*50}")
    print(f"Load from files complete!")
    print(f"  Files processed: {stats['files_processed']}")
    print(f"  Total studies: {stats['total_studies']:,}")
    print(f"  Loaded successfully: {stats['loaded_success']:,}")
    print(f"  Failed: {stats['loaded_failure']:,}")
    print(f"{'='*50}")
    
    return stats


# CLI entry point
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Bulk download ClinicalTrials.gov data")
    parser.add_argument(
        "--mode",
        choices=["download", "load", "both"],
        default="both",
        help="download=save to files only, load=load from files, both=download and load to DB"
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Optional search query to filter studies (e.g., 'cancer')"
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/raw",
        help="Directory for raw JSON files"
    )
    
    args = parser.parse_args()
    
    if args.mode == "download":
        asyncio.run(bulk_download_to_files(args.data_dir, args.query))
    elif args.mode == "load":
        asyncio.run(load_from_files(args.data_dir))
    else:  # both
        asyncio.run(bulk_download_to_database(args.query, save_raw=True))
