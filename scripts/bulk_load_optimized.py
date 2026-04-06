"""
Optimized bulk loader for 500K+ clinical trials.

Optimizations:
1. Concurrent batch processing with asyncio
2. Bulk upserts (multiple records per API call)
3. Progress checkpointing for resume capability
4. Rate limiting to avoid API throttling
5. Memory-efficient streaming JSON parser
6. Connection reuse

Usage:
    python scripts/bulk_load_optimized.py ctg-studies_full.json
    python scripts/bulk_load_optimized.py ctg-studies_full.json --resume  # Resume from checkpoint
"""

import asyncio
import json
import time
import ijson
from pathlib import Path
from datetime import datetime
from typing import Iterator, Any
from dataclasses import dataclass, asdict
import argparse

from src.db.supabase_client import get_supabase_admin_client
from src.ingestion.parser import parse_study, normalize_facility_name


@dataclass
class LoadProgress:
    """Track loading progress for checkpointing."""
    total_processed: int = 0
    trials_loaded: int = 0
    sites_loaded: int = 0
    investigators_loaded: int = 0
    errors: int = 0
    start_time: str = ""
    last_checkpoint: str = ""
    last_nct_id: str = ""
    
    def save(self, filepath: str = ".bulk_load_checkpoint.json"):
        self.last_checkpoint = datetime.now().isoformat()
        with open(filepath, 'w') as f:
            json.dump(asdict(self), f, indent=2)
    
    @classmethod
    def load(cls, filepath: str = ".bulk_load_checkpoint.json") -> "LoadProgress":
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
                return cls(**data)
        except FileNotFoundError:
            return cls(start_time=datetime.now().isoformat())


class OptimizedBulkLoader:
    """
    Optimized loader for large-scale clinical trial data ingestion.
    """
    
    def __init__(
        self,
        batch_size: int = 50,
        max_concurrent: int = 3,
        checkpoint_interval: int = 1000,
        rate_limit_delay: float = 0.1,
    ):
        self.client = get_supabase_admin_client()
        self.batch_size = batch_size
        self.max_concurrent = max_concurrent
        self.checkpoint_interval = checkpoint_interval
        self.rate_limit_delay = rate_limit_delay
        
        # Caches to avoid duplicate lookups
        self._site_cache: dict[str, int] = {}
        self._investigator_cache: dict[str, int] = {}
        
        # Semaphore for concurrency control
        self._semaphore = asyncio.Semaphore(max_concurrent)
        
        # Progress tracking
        self.progress = LoadProgress(start_time=datetime.now().isoformat())
    
    def _site_key(self, site: dict) -> str:
        return f"{site.get('facility_name')}|{site.get('city')}|{site.get('country')}"
    
    def _investigator_key(self, inv: dict) -> str:
        return f"{inv.get('full_name')}|{inv.get('affiliation')}"
    
    async def bulk_upsert_trials(self, trials: list[dict]) -> dict[str, int]:
        """Bulk upsert trials, return mapping of nct_id -> id."""
        if not trials:
            return {}
        
        # Clean data
        clean_trials = []
        for t in trials:
            clean = {k: v for k, v in t.items() if k != 'raw_json' and v is not None}
            clean_trials.append(clean)
        
        try:
            result = self.client.table("trials").upsert(
                clean_trials,
                on_conflict="nct_id"
            ).execute()
            
            return {r["nct_id"]: r["id"] for r in result.data}
        except Exception as e:
            print(f"Error bulk upserting trials: {e}")
            return {}
    
    async def bulk_upsert_sites(self, sites: list[dict]) -> dict[str, int]:
        """Bulk upsert sites, return mapping of cache_key -> id."""
        if not sites:
            return {}
        
        # Deduplicate by cache key
        unique_sites = {}
        for site in sites:
            key = self._site_key(site)
            if key not in unique_sites and key not in self._site_cache:
                site_data = {
                    "facility_name": site.get("facility_name"),
                    "facility_name_normalized": site.get("facility_name_normalized"),
                    "city": site.get("city"),
                    "state": site.get("state"),
                    "country": site.get("country"),
                    "zip": site.get("zip"),
                }
                unique_sites[key] = {k: v for k, v in site_data.items() if v is not None}
        
        if not unique_sites:
            return {}
        
        try:
            result = self.client.table("sites").upsert(
                list(unique_sites.values()),
                on_conflict="facility_name,city,country"
            ).execute()
            
            # Map results back to cache keys
            result_map = {}
            for r in result.data:
                key = f"{r['facility_name']}|{r['city']}|{r['country']}"
                result_map[key] = r["id"]
                self._site_cache[key] = r["id"]
            
            return result_map
        except Exception as e:
            print(f"Error bulk upserting sites: {e}")
            return {}
    
    async def bulk_upsert_investigators(self, investigators: list[dict]) -> dict[str, int]:
        """Bulk upsert investigators, return mapping of cache_key -> id."""
        if not investigators:
            return {}
        
        # Deduplicate by cache key
        unique_invs = {}
        for inv in investigators:
            key = self._investigator_key(inv)
            if key not in unique_invs and key not in self._investigator_cache:
                inv_data = {
                    "full_name": inv.get("full_name"),
                    "name_normalized": inv.get("name_normalized"),
                    "role": inv.get("role"),
                    "affiliation": inv.get("affiliation"),
                    "affiliation_normalized": inv.get("affiliation_normalized"),
                }
                unique_invs[key] = {k: v for k, v in inv_data.items() if v is not None}
        
        if not unique_invs:
            return {}
        
        try:
            result = self.client.table("investigators").upsert(
                list(unique_invs.values()),
                on_conflict="full_name,affiliation"
            ).execute()
            
            result_map = {}
            for r in result.data:
                key = f"{r['full_name']}|{r.get('affiliation', '')}"
                result_map[key] = r["id"]
                self._investigator_cache[key] = r["id"]
            
            return result_map
        except Exception as e:
            print(f"Error bulk upserting investigators: {e}")
            return {}
    
    async def bulk_upsert_relationships(
        self,
        table: str,
        records: list[dict],
        conflict_columns: str,
    ) -> int:
        """Bulk upsert relationship records."""
        if not records:
            return 0
        
        try:
            # Deduplicate
            seen = set()
            unique = []
            for r in records:
                key = tuple(r.get(c) for c in conflict_columns.split(","))
                if key not in seen:
                    seen.add(key)
                    unique.append(r)
            
            self.client.table(table).upsert(
                unique,
                on_conflict=conflict_columns
            ).execute()
            return len(unique)
        except Exception as e:
            print(f"Error bulk upserting {table}: {e}")
            return 0
    
    async def process_batch(self, studies: list[dict]) -> tuple[int, int]:
        """
        Process a batch of studies with bulk operations.
        
        Returns: (success_count, error_count)
        """
        async with self._semaphore:
            try:
                # Parse all studies
                parsed_studies = []
                for study in studies:
                    try:
                        parsed = parse_study(study)
                        parsed_studies.append(parsed)
                    except Exception as e:
                        print(f"Parse error: {e}")
                
                if not parsed_studies:
                    return 0, len(studies)
                
                # Collect all entities
                all_trials = [p["trial"] for p in parsed_studies]
                all_sites = []
                all_investigators = []
                
                for p in parsed_studies:
                    all_sites.extend(p["sites"])
                    all_investigators.extend(p["overall_officials"])
                    all_investigators.extend(p["site_contacts"])
                
                # Bulk upsert entities
                trial_ids = await self.bulk_upsert_trials(all_trials)
                await self.bulk_upsert_sites(all_sites)
                await self.bulk_upsert_investigators(all_investigators)
                
                # Rate limit
                await asyncio.sleep(self.rate_limit_delay)
                
                # Build relationships
                trial_sites = []
                trial_investigators = []
                investigator_sites = []
                
                for parsed in parsed_studies:
                    trial_nct = parsed["trial"]["nct_id"]
                    trial_id = trial_ids.get(trial_nct)
                    if not trial_id:
                        continue
                    
                    # Map site index to site_id
                    site_ids_by_index = {}
                    for site in parsed["sites"]:
                        site_key = self._site_key(site)
                        site_id = self._site_cache.get(site_key)
                        if site_id:
                            site_ids_by_index[site.get("_location_index")] = site_id
                            trial_sites.append({
                                "trial_id": trial_id,
                                "site_id": site_id,
                                "recruitment_status": site.get("recruitment_status"),
                            })
                    
                    # Overall officials
                    for official in parsed["overall_officials"]:
                        inv_key = self._investigator_key(official)
                        inv_id = self._investigator_cache.get(inv_key)
                        if not inv_id:
                            continue
                        
                        trial_investigators.append({
                            "trial_id": trial_id,
                            "investigator_id": inv_id,
                            "role": official.get("role"),
                        })
                        
                        # Link to all sites (oversight)
                        for site_idx, site_id in site_ids_by_index.items():
                            investigator_sites.append({
                                "investigator_id": inv_id,
                                "site_id": site_id,
                                "trial_id": trial_id,
                                "link_type": "oversight",
                            })
                    
                    # Site contacts
                    for contact in parsed["site_contacts"]:
                        site_idx = contact.get("_site_index")
                        site_id = site_ids_by_index.get(site_idx)
                        if not site_id:
                            continue
                        
                        # Find site name for affiliation
                        site_name = None
                        for site in parsed["sites"]:
                            if site.get("_location_index") == site_idx:
                                site_name = site.get("facility_name")
                                break
                        
                        contact_inv = {
                            "full_name": contact.get("full_name"),
                            "name_normalized": contact.get("name_normalized"),
                            "role": contact.get("role"),
                            "affiliation": site_name,
                            "affiliation_normalized": normalize_facility_name(site_name),
                        }
                        inv_key = self._investigator_key(contact_inv)
                        inv_id = self._investigator_cache.get(inv_key)
                        
                        if inv_id:
                            trial_investigators.append({
                                "trial_id": trial_id,
                                "investigator_id": inv_id,
                                "role": contact.get("role"),
                            })
                            investigator_sites.append({
                                "investigator_id": inv_id,
                                "site_id": site_id,
                                "trial_id": trial_id,
                                "link_type": "site_contact",
                            })
                
                # Bulk upsert relationships
                await self.bulk_upsert_relationships(
                    "trial_sites", trial_sites, "trial_id,site_id"
                )
                await self.bulk_upsert_relationships(
                    "trial_investigators", trial_investigators, "trial_id,investigator_id"
                )
                await self.bulk_upsert_relationships(
                    "investigator_sites", investigator_sites, "investigator_id,site_id,trial_id,link_type"
                )
                
                return len(trial_ids), len(studies) - len(trial_ids)
                
            except Exception as e:
                print(f"Batch error: {e}")
                return 0, len(studies)


def stream_studies(filepath: str, skip_count: int = 0) -> Iterator[dict]:
    """Stream studies from JSON file."""
    with open(filepath, 'rb') as f:
        first_char = f.read(1)
        f.seek(0)
        
        if first_char == b'[':
            parser = ijson.items(f, 'item')
        else:
            parser = ijson.items(f, 'studies.item')
        
        for i, study in enumerate(parser):
            if i < skip_count:
                continue
            yield study


async def run_bulk_load(
    filepath: str,
    batch_size: int = 50,
    max_concurrent: int = 3,
    resume: bool = False,
):
    """Run the optimized bulk load."""
    
    # Load or create progress
    if resume:
        progress = LoadProgress.load()
        print(f"Resuming from checkpoint: {progress.total_processed} studies processed")
        skip_count = progress.total_processed
    else:
        progress = LoadProgress(start_time=datetime.now().isoformat())
        skip_count = 0
    
    loader = OptimizedBulkLoader(
        batch_size=batch_size,
        max_concurrent=max_concurrent,
        checkpoint_interval=1000,
    )
    loader.progress = progress
    
    print(f"\n{'='*60}")
    print(f"Starting bulk load: {filepath}")
    print(f"  Batch size: {batch_size}")
    print(f"  Max concurrent: {max_concurrent}")
    print(f"  Skip count: {skip_count}")
    print(f"{'='*60}\n")
    
    start_time = time.time()
    batch = []
    batch_tasks = []
    
    for study in stream_studies(filepath, skip_count):
        batch.append(study)
        
        if len(batch) >= batch_size:
            # Process batch
            success, errors = await loader.process_batch(batch)
            
            progress.total_processed += len(batch)
            progress.trials_loaded += success
            progress.errors += errors
            
            if batch:
                progress.last_nct_id = batch[-1].get("protocolSection", {}).get("identificationModule", {}).get("nctId", "")
            
            # Progress update
            elapsed = time.time() - start_time
            rate = progress.total_processed / elapsed if elapsed > 0 else 0
            
            print(f"Processed: {progress.total_processed:,} | "
                  f"Success: {progress.trials_loaded:,} | "
                  f"Errors: {progress.errors:,} | "
                  f"Rate: {rate:.1f}/sec | "
                  f"Cache: {len(loader._site_cache):,} sites, {len(loader._investigator_cache):,} PIs")
            
            # Checkpoint
            if progress.total_processed % loader.checkpoint_interval == 0:
                progress.save()
                print(f"  [Checkpoint saved]")
            
            batch = []
    
    # Process remaining
    if batch:
        success, errors = await loader.process_batch(batch)
        progress.total_processed += len(batch)
        progress.trials_loaded += success
        progress.errors += errors
    
    # Final checkpoint
    progress.save()
    
    elapsed = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"Bulk load complete!")
    print(f"  Total processed: {progress.total_processed:,}")
    print(f"  Trials loaded: {progress.trials_loaded:,}")
    print(f"  Errors: {progress.errors:,}")
    print(f"  Time: {elapsed/60:.1f} minutes")
    print(f"  Rate: {progress.total_processed/elapsed:.1f} studies/sec")
    print(f"{'='*60}")


if __name__ == "__main__":
    import sys
    # Force unbuffered output
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
    
    parser = argparse.ArgumentParser(description="Optimized bulk loader for clinical trials")
    parser.add_argument("filepath", help="Path to JSON file")
    parser.add_argument("--batch-size", type=int, default=50, help="Studies per batch (default: 50)")
    parser.add_argument("--concurrent", type=int, default=3, help="Max concurrent batches (default: 3)")
    parser.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    
    args = parser.parse_args()
    
    asyncio.run(run_bulk_load(
        filepath=args.filepath,
        batch_size=args.batch_size,
        max_concurrent=args.concurrent,
        resume=args.resume,
    ))
