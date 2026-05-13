#!/usr/bin/env python3
"""
Step 3: Enrich Subset PIs

Runs ORCID + Semantic Scholar enrichment on the subset investigators.
Uses the investigator IDs from 02_get_subset_trials.py.

Usage:
    PYTHONPATH=. python scripts/v2_test/03_enrich_subset_pis.py
    PYTHONPATH=. python scripts/v2_test/03_enrich_subset_pis.py --limit 100  # Test with small batch
    PYTHONPATH=. python scripts/v2_test/03_enrich_subset_pis.py --skip-orcid  # S2 only
"""

import os
import sys
import json
import asyncio
import argparse
from pathlib import Path

from dotenv import load_dotenv
import requests

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

# Import the enrichment functions from the main script
from scripts.enrich_investigators_s2 import (
    SemanticScholarClient,
    OrcidClient,
    enrich_batch,
    is_likely_sponsor,
    CONCURRENT_REQUESTS,
    S2_API_KEY,
    ORCID_CLIENT_ID,
    ORCID_CLIENT_SECRET,
    S2_REQUESTS_PER_SECOND,
    ORCID_REQUESTS_PER_SECOND,
)

# Data directory
DATA_DIR = Path(__file__).parent / "data"

# Supabase config
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")


class SimpleSupabaseClient:
    """Simple Supabase client using requests."""
    
    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    def table(self, name: str):
        """Return a table query builder."""
        return TableQuery(self.url, self.headers, name)


class TableQuery:
    """Simple table query builder."""
    
    def __init__(self, url: str, headers: dict, table: str):
        self.url = url
        self.headers = headers
        self.table = table
        self._select = "*"
        self._filters = []
        self._limit = None
    
    def select(self, columns: str):
        self._select = columns
        return self
    
    def in_(self, column: str, values: list):
        values_str = ",".join(str(v) for v in values)
        self._filters.append(f"{column}=in.({values_str})")
        return self
    
    def eq(self, column: str, value):
        self._filters.append(f"{column}=eq.{value}")
        return self
    
    def limit(self, n: int):
        self._limit = n
        return self
    
    def execute(self):
        url = f"{self.url}/rest/v1/{self.table}?select={self._select}"
        for f in self._filters:
            url += f"&{f}"
        if self._limit:
            url += f"&limit={self._limit}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return type('Response', (), {'data': response.json()})()
    
    def update(self, data: dict):
        return UpdateQuery(self.url, self.headers, self.table, self._filters, data)


class UpdateQuery:
    """Simple update query."""
    
    def __init__(self, url: str, headers: dict, table: str, filters: list, data: dict):
        self.url = url
        self.headers = headers
        self.table = table
        self.filters = filters
        self.data = data
    
    def eq(self, column: str, value):
        self.filters.append(f"{column}=eq.{value}")
        return self
    
    def execute(self):
        url = f"{self.url}/rest/v1/{self.table}"
        for i, f in enumerate(self.filters):
            url += ("?" if i == 0 else "&") + f
        response = requests.patch(url, headers=self.headers, json=self.data)
        response.raise_for_status()
        return type('Response', (), {'data': response.json()})()


def get_supabase_admin_client():
    return SimpleSupabaseClient(SUPABASE_URL, SUPABASE_KEY)


def load_subset_investigator_ids() -> list[int]:
    """Load investigator IDs from previous step."""
    ids_file = DATA_DIR / "subset_investigator_ids.json"
    
    if not ids_file.exists():
        print(f"❌ Error: {ids_file} not found!")
        print("   Run 02_get_subset_trials.py first.")
        sys.exit(1)
    
    with open(ids_file) as f:
        return json.load(f)


async def main(args):
    """Main enrichment loop for subset."""
    
    # Check API keys
    if S2_API_KEY:
        print(f"✅ S2 API key found (rate: {S2_REQUESTS_PER_SECOND} req/sec)")
    else:
        print(f"⚠️  No S2 API key - using public API (rate: 1 req/sec)")
    
    use_orcid = not args.skip_orcid
    if use_orcid:
        if ORCID_CLIENT_ID and ORCID_CLIENT_SECRET:
            print(f"✅ ORCID credentials found (rate: {ORCID_REQUESTS_PER_SECOND} req/sec)")
        else:
            print("⚠️  ORCID credentials not found - using S2 only")
            use_orcid = False
    else:
        print("ℹ️  ORCID lookup disabled (--skip-orcid)")
    
    # Load subset investigator IDs
    investigator_ids = load_subset_investigator_ids()
    print(f"\n📋 Loaded {len(investigator_ids):,} investigator IDs from subset")
    
    if args.limit:
        investigator_ids = investigator_ids[:args.limit]
        print(f"   Limited to {len(investigator_ids):,} (--limit {args.limit})")
    
    # Get investigator details from database
    supabase = get_supabase_admin_client()
    
    print("\n📥 Fetching investigator details...")
    investigators = []
    batch_size = 500
    
    for i in range(0, len(investigator_ids), batch_size):
        batch_ids = investigator_ids[i:i + batch_size]
        
        result = supabase.table("investigators").select(
            "id, full_name, affiliation"
        ).in_("id", batch_ids).execute()
        
        investigators.extend(result.data)
        print(f"   Fetched {len(investigators):,} investigators...")
    
    # Filter out sponsors/organizations
    original_count = len(investigators)
    investigators = [
        inv for inv in investigators 
        if not is_likely_sponsor(inv["full_name"])
        and len(inv["full_name"]) > 5
    ]
    print(f"   Filtered: {original_count} → {len(investigators)} (removed sponsors/orgs)")
    
    if not investigators:
        print("\n✅ No investigators to process!")
        return
    
    # Process
    print(f"\n🚀 Starting ORCID + S2 enrichment")
    print(f"   Investigators: {len(investigators):,}")
    print(f"   Batch size: {args.batch_size}")
    print(f"   ORCID enabled: {use_orcid}")
    
    total_matched = 0
    total_failed = 0
    total_orcid_matched = 0
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
    
    async with SemanticScholarClient(S2_API_KEY) as s2_client:
        orcid_client = None
        if use_orcid:
            orcid_client = OrcidClient(ORCID_CLIENT_ID, ORCID_CLIENT_SECRET)
            await orcid_client.__aenter__()
        
        try:
            for i in range(0, len(investigators), args.batch_size):
                batch = investigators[i:i + args.batch_size]
                batch_num = i // args.batch_size + 1
                total_batches = (len(investigators) + args.batch_size - 1) // args.batch_size
                
                print(f"\n🔄 Batch {batch_num}/{total_batches} ({len(batch)} investigators)")
                
                matched, failed, orcid_matched = await enrich_batch(
                    s2_client, orcid_client, supabase, batch, semaphore, use_orcid
                )
                
                total_matched += matched
                total_failed += failed
                total_orcid_matched += orcid_matched
                
                # Progress
                match_rate = (matched / len(batch) * 100) if batch else 0
                orcid_rate = (orcid_matched / matched * 100) if matched else 0
                print(f"   ✓ Matched: {matched}/{len(batch)} ({match_rate:.1f}%)")
                if use_orcid:
                    print(f"   ✓ Via ORCID: {orcid_matched}/{matched} ({orcid_rate:.1f}%)")
                print(f"   Total: {total_matched:,} matched, {total_failed:,} failed")
                
        finally:
            if orcid_client:
                await orcid_client.__aexit__(None, None, None)
    
    # Final summary
    print(f"\n{'='*50}")
    print(f"✅ Subset enrichment complete!")
    print(f"   Total processed: {total_matched + total_failed:,}")
    total = total_matched + total_failed
    match_pct = (total_matched / total * 100) if total else 0
    print(f"   Matched: {total_matched:,} ({match_pct:.1f}%)")
    if use_orcid and total_matched > 0:
        orcid_pct = (total_orcid_matched / total_matched * 100)
        print(f"   Via ORCID: {total_orcid_matched:,} ({orcid_pct:.1f}%)")
        print(f"   Via S2 name: {total_matched - total_orcid_matched:,}")
    print(f"   Failed: {total_failed:,}")
    
    # Save results
    results = {
        "total_processed": total_matched + total_failed,
        "matched": total_matched,
        "match_rate": match_pct,
        "orcid_matched": total_orcid_matched,
        "failed": total_failed,
    }
    results_file = DATA_DIR / "enrichment_results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Results saved to {results_file}")
    print("\n✅ Complete! Next: run 04_compute_derived_fields.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich subset investigators with ORCID + S2")
    parser.add_argument("--limit", type=int, help="Limit number of investigators to process")
    parser.add_argument("--batch-size", type=int, default=50, help="Batch size")
    parser.add_argument("--skip-orcid", action="store_true", help="Skip ORCID lookup, use S2 only")
    
    args = parser.parse_args()
    asyncio.run(main(args))
