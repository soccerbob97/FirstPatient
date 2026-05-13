#!/usr/bin/env python3
"""
Step 3: Enrich Subset PIs with OpenAlex

Uses OpenAlex API (free, no key required) to enrich investigators with:
- h-index, paper count, citation count
- Research topics/areas
- ORCID ID (if available)
- Affiliations

Rate limit: 100,000 calls/day, 10 requests/second (no auth required)

Usage:
    PYTHONPATH=. python scripts/v2_test/03_enrich_openalex.py
    PYTHONPATH=. python scripts/v2_test/03_enrich_openalex.py --limit 100  # Test with small batch
"""

import os
import sys
import json
import asyncio
import aiohttp
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional
import time

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.db.supabase_client import get_supabase_admin_client

# Data directory
DATA_DIR = Path(__file__).parent / "data"

# OpenAlex API config
OPENALEX_BASE_URL = "https://api.openalex.org"
REQUESTS_PER_SECOND = 8  # Stay under 10/sec limit
CONCURRENT_REQUESTS = 5
BATCH_SIZE = 50

# Polite pool - add email for better rate limits
USER_EMAIL = os.getenv("OPENALEX_EMAIL", "")


class OpenAlexClient:
    """Async client for OpenAlex API."""
    
    def __init__(self, email: str = ""):
        self.base_url = OPENALEX_BASE_URL
        self.email = email
        self.session: Optional[aiohttp.ClientSession] = None
        self.last_request_time = 0
        self.min_interval = 1.0 / REQUESTS_PER_SECOND
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def _rate_limit(self):
        """Enforce rate limiting."""
        now = time.time()
        elapsed = now - self.last_request_time
        if elapsed < self.min_interval:
            await asyncio.sleep(self.min_interval - elapsed)
        self.last_request_time = time.time()
    
    async def search_author(self, name: str, affiliation: str = None, retry_count: int = 0) -> Optional[dict]:
        """
        Search for an author by name and optionally affiliation.
        Returns the best match with h-index, citations, etc.
        """
        if retry_count > 3:
            return None
            
        await self._rate_limit()
        
        # Clean name - remove titles like MD, PhD, etc.
        clean_name = self._clean_name(name)
        if not clean_name or len(clean_name) < 3:
            return None
        
        # Build search query
        params = {
            "search": clean_name,
            "per_page": 5,
        }
        
        # Add email for polite pool
        if self.email:
            params["mailto"] = self.email
        
        url = f"{self.base_url}/authors"
        
        try:
            async with self.session.get(url, params=params, timeout=15) as resp:
                if resp.status == 429:
                    # Rate limited - wait and retry with limit
                    await asyncio.sleep(2)
                    return await self.search_author(name, affiliation, retry_count + 1)
                
                if resp.status != 200:
                    return None
                
                data = await resp.json()
                results = data.get("results", [])
                
                if not results:
                    return None
                
                # If we have affiliation, try to match
                if affiliation:
                    best_match = self._match_by_affiliation(results, affiliation)
                    if best_match:
                        return self._extract_author_data(best_match)
                
                # Otherwise return top result if it has reasonable metrics
                top = results[0]
                if top.get("works_count", 0) > 0:
                    return self._extract_author_data(top)
                
                return None
                
        except Exception as e:
            print(f"    Error searching {name}: {e}")
            return None
    
    def _clean_name(self, name: str) -> str:
        """Remove titles and clean name for search."""
        # Remove common titles
        titles = [
            "MD", "M.D.", "PhD", "Ph.D.", "Dr.", "Prof.", "Professor",
            "DO", "D.O.", "MPH", "M.P.H.", "MS", "M.S.", "MSc", "M.Sc.",
            "MBA", "M.B.A.", "RN", "R.N.", "BSN", "B.S.N.", "DNP", "D.N.P.",
            "FACS", "FACP", "FACR", "FAHA", "FCCP", "FRCP", "FRS",
            "Jr.", "Jr", "Sr.", "Sr", "III", "II", "IV",
            "Medical Director", "Principal Investigator", "PI",
            "Associate Professor", "Assistant Professor", "A. Professor",
            "MBChB", "MBBS", "MBBCh", "MRCP", "FRCS",
        ]
        
        result = name
        for title in titles:
            result = result.replace(f", {title}", "")
            result = result.replace(f" {title}", "")
            result = result.replace(f"{title},", "")
            result = result.replace(f"{title} ", "")
        
        # Remove extra whitespace and commas
        result = " ".join(result.split())
        result = result.strip(" ,.")
        
        return result
    
    def _match_by_affiliation(self, results: list, affiliation: str) -> Optional[dict]:
        """Find best match based on affiliation similarity."""
        if not affiliation:
            return None
        
        aff_lower = affiliation.lower()
        aff_words = set(aff_lower.split())
        
        best_match = None
        best_score = 0
        
        for author in results:
            affiliations = author.get("affiliations", [])
            for aff in affiliations:
                inst = aff.get("institution", {})
                inst_name = inst.get("display_name", "").lower()
                
                # Count matching words
                inst_words = set(inst_name.split())
                common = len(aff_words & inst_words)
                
                if common > best_score:
                    best_score = common
                    best_match = author
        
        # Require at least 1 word match
        if best_score >= 1:
            return best_match
        
        return None
    
    def _extract_author_data(self, author: dict) -> dict:
        """Extract relevant fields from OpenAlex author response."""
        stats = author.get("summary_stats", {})
        
        # Extract topics/research areas
        topics = []
        for topic in author.get("topics", [])[:5]:
            topic_name = topic.get("display_name")
            if topic_name:
                topics.append(topic_name)
        
        # Extract affiliations
        affiliations = []
        for aff in author.get("affiliations", [])[:3]:
            inst = aff.get("institution", {})
            inst_name = inst.get("display_name")
            if inst_name:
                affiliations.append(inst_name)
        
        # Extract ORCID if available
        orcid = None
        orcid_url = author.get("orcid")
        if orcid_url:
            # Extract ID from URL like "https://orcid.org/0000-0002-1478-4729"
            orcid = orcid_url.split("/")[-1]
        
        return {
            "openalex_id": author.get("id", "").replace("https://openalex.org/", ""),
            "h_index": stats.get("h_index"),
            "paper_count": author.get("works_count"),
            "citation_count": author.get("cited_by_count"),
            "i10_index": stats.get("i10_index"),
            "research_areas": topics,
            "affiliations_openalex": affiliations,
            "orcid_id": orcid,
        }


def load_subset_investigator_ids() -> list[int]:
    """Load investigator IDs from previous step."""
    ids_file = DATA_DIR / "subset_investigator_ids.json"
    
    if not ids_file.exists():
        print(f"❌ Error: {ids_file} not found!")
        print("   Run 02_get_subset_trials.py first.")
        sys.exit(1)
    
    with open(ids_file) as f:
        return json.load(f)


def is_likely_sponsor(name: str) -> bool:
    """Check if name looks like a sponsor/organization rather than a person."""
    name_lower = name.lower()
    sponsor_keywords = [
        'clinical', 'pharma', 'inc', 'llc', 'ltd', 'center', 'centre',
        'transparency', 'trials', 'research group', 'registry', 'gcr',
        'global', 'coordinator', 'gsk', 'glaxo', 'pfizer', 'novartis',
        'merck', 'sanofi', 'astrazeneca', 'roche', 'lilly', 'bristol',
        'johnson', 'abbvie', 'amgen', 'biogen', 'gilead', 'boehringer',
        'medical director', 'use central contact', 'contact',
        'biontech', 'responsible person', 'icd csd',
    ]
    return any(kw in name_lower for kw in sponsor_keywords)


async def enrich_investigator(
    client: OpenAlexClient,
    supabase,
    inv: dict,
    semaphore: asyncio.Semaphore
) -> bool:
    """Enrich a single investigator. Returns True if matched."""
    async with semaphore:
        try:
            result = await client.search_author(
                inv["full_name"],
                inv.get("affiliation")
            )
            
            if not result:
                return False
            
            # Update database
            update_data = {
                "semantic_scholar_id": result["openalex_id"],  # Reuse column
                "h_index": result["h_index"],
                "paper_count": result["paper_count"],
                "citation_count": result["citation_count"],
                "research_areas": result["research_areas"],
                "affiliations_s2": result["affiliations_openalex"],  # Reuse column
                "s2_match_source": "openalex",  # Track source
                "s2_enriched_at": datetime.now().isoformat(),
            }
            
            # Add ORCID if found and not already set
            if result.get("orcid_id") and not inv.get("orcid_id"):
                update_data["orcid_id"] = result["orcid_id"]
            
            supabase.table("investigators").update(update_data).eq("id", inv["id"]).execute()
            return True
            
        except Exception as e:
            print(f"    Error enriching {inv['full_name']}: {e}")
            return False


async def main(args):
    """Main enrichment loop."""
    
    print("🚀 OpenAlex PI Enrichment")
    print(f"   Rate: {REQUESTS_PER_SECOND} req/sec")
    print(f"   Concurrent: {CONCURRENT_REQUESTS}")
    
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
    fetch_batch_size = 500
    
    for i in range(0, len(investigator_ids), fetch_batch_size):
        batch_ids = investigator_ids[i:i + fetch_batch_size]
        
        result = supabase.table("investigators").select(
            "id, full_name, affiliation, orcid_id, s2_enriched_at"
        ).in_("id", batch_ids).execute()
        
        investigators.extend(result.data)
        print(f"   Fetched {len(investigators):,} investigators...")
    
    # Filter out sponsors/organizations and already enriched
    original_count = len(investigators)
    investigators = [
        inv for inv in investigators 
        if not is_likely_sponsor(inv["full_name"])
        and len(inv["full_name"]) > 5
        and not inv.get("s2_enriched_at")  # Skip already enriched
    ]
    print(f"   Filtered: {original_count} → {len(investigators)} (removed sponsors/already enriched)")
    
    if not investigators:
        print("\n✅ No investigators to process!")
        return
    
    # Estimate time
    est_seconds = len(investigators) / REQUESTS_PER_SECOND
    est_minutes = est_seconds / 60
    print(f"\n⏱️  Estimated time: {est_minutes:.1f} minutes")
    
    # Process
    print(f"\n🔄 Starting OpenAlex enrichment...")
    
    total_matched = 0
    total_failed = 0
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
    
    async with OpenAlexClient(USER_EMAIL) as client:
        # Process in batches for progress reporting
        for batch_start in range(0, len(investigators), BATCH_SIZE):
            batch = investigators[batch_start:batch_start + BATCH_SIZE]
            batch_num = batch_start // BATCH_SIZE + 1
            total_batches = (len(investigators) + BATCH_SIZE - 1) // BATCH_SIZE
            
            print(f"\n🔄 Batch {batch_num}/{total_batches} ({len(batch)} investigators)")
            
            # Process batch concurrently
            tasks = [
                enrich_investigator(client, supabase, inv, semaphore)
                for inv in batch
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Count results
            batch_matched = sum(1 for r in results if r is True)
            batch_failed = len(batch) - batch_matched
            
            total_matched += batch_matched
            total_failed += batch_failed
            
            match_rate = (batch_matched / len(batch) * 100) if batch else 0
            print(f"   ✓ Matched: {batch_matched}/{len(batch)} ({match_rate:.1f}%)")
            print(f"   Total: {total_matched:,} matched, {total_failed:,} failed")
    
    # Final summary
    total = total_matched + total_failed
    match_pct = (total_matched / total * 100) if total else 0
    
    print(f"\n{'='*50}")
    print(f"✅ OpenAlex enrichment complete!")
    print(f"   Total processed: {total:,}")
    print(f"   Matched: {total_matched:,} ({match_pct:.1f}%)")
    print(f"   Failed: {total_failed:,}")
    
    # Save results
    results = {
        "source": "openalex",
        "total_processed": total,
        "matched": total_matched,
        "match_rate": match_pct,
        "failed": total_failed,
        "timestamp": datetime.now().isoformat(),
    }
    results_file = DATA_DIR / "enrichment_results.json"
    with open(results_file, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n💾 Results saved to {results_file}")
    print("\n✅ Complete! Next: run 05_generate_embeddings.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich subset investigators with OpenAlex")
    parser.add_argument("--limit", type=int, help="Limit number of investigators to process")
    
    args = parser.parse_args()
    asyncio.run(main(args))
