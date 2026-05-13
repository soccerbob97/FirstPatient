#!/usr/bin/env python3
"""
Step 3: Enrich Subset PIs with OpenAlex (V2 - Robust Version)

Simplified synchronous version with:
- No async complexity
- Verbose error logging
- Single request at a time
- Automatic retry with backoff

Usage:
    PYTHONPATH=. python scripts/v2_test/03_enrich_openalex_v2.py
    PYTHONPATH=. python scripts/v2_test/03_enrich_openalex_v2.py --limit 100
"""

import os
import sys
import json
import requests
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
REQUEST_DELAY = 0.15  # 150ms between requests (~6.6/sec, well under 10/sec limit)

# Polite pool - add email for better rate limits
USER_EMAIL = os.getenv("OPENALEX_EMAIL", "")


def clean_name(name: str) -> str:
    """Remove titles and clean name for search."""
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
    
    result = " ".join(result.split())
    result = result.strip(" ,.")
    return result


def search_author(name: str, affiliation: str = None, retry_count: int = 0) -> Optional[dict]:
    """Search for an author by name. Returns enrichment data or None."""
    if retry_count > 3:
        return None
    
    clean = clean_name(name)
    if not clean or len(clean) < 3:
        return None
    
    params = {"search": clean, "per_page": 5}
    if USER_EMAIL:
        params["mailto"] = USER_EMAIL
    
    try:
        resp = requests.get(
            f"{OPENALEX_BASE_URL}/authors",
            params=params,
            timeout=15
        )
        
        if resp.status_code == 429:
            # Rate limited - wait and retry
            print(f"    Rate limited, waiting 5s...")
            time.sleep(5)
            return search_author(name, affiliation, retry_count + 1)
        
        if resp.status_code != 200:
            print(f"    API error {resp.status_code}: {resp.text[:100]}")
            return None
        
        data = resp.json()
        
        # Check for API error in response
        if "error" in data:
            print(f"    API error: {data['error']}")
            return None
        
        results = data.get("results", [])
        if not results:
            return None
        
        # Find best match
        best = None
        if affiliation:
            best = match_by_affiliation(results, affiliation)
        
        if not best:
            top = results[0]
            if top.get("works_count", 0) > 0:
                best = top
        
        if not best:
            return None
        
        # Extract data
        stats = best.get("summary_stats", {})
        
        topics = []
        for topic in best.get("topics", [])[:5]:
            if topic.get("display_name"):
                topics.append(topic["display_name"])
        
        affiliations = []
        for aff in best.get("affiliations", [])[:3]:
            inst = aff.get("institution", {})
            if inst.get("display_name"):
                affiliations.append(inst["display_name"])
        
        orcid = None
        if best.get("orcid"):
            orcid = best["orcid"].split("/")[-1]
        
        return {
            "openalex_id": best.get("id", "").replace("https://openalex.org/", ""),
            "h_index": stats.get("h_index"),
            "paper_count": best.get("works_count"),
            "citation_count": best.get("cited_by_count"),
            "research_areas": topics,
            "affiliations_openalex": affiliations,
            "orcid_id": orcid,
        }
        
    except requests.exceptions.Timeout:
        print(f"    Timeout, retrying...")
        time.sleep(2)
        return search_author(name, affiliation, retry_count + 1)
    except Exception as e:
        print(f"    Error: {type(e).__name__}: {e}")
        return None


def match_by_affiliation(results: list, affiliation: str) -> Optional[dict]:
    """Find best match based on affiliation similarity."""
    if not affiliation:
        return None
    
    aff_lower = affiliation.lower()
    aff_words = set(aff_lower.split())
    
    best_match = None
    best_score = 0
    
    for author in results:
        for aff in author.get("affiliations", []):
            inst = aff.get("institution", {})
            inst_name = inst.get("display_name", "").lower()
            inst_words = set(inst_name.split())
            common = len(aff_words & inst_words)
            
            if common > best_score:
                best_score = common
                best_match = author
    
    return best_match if best_score >= 1 else None


def is_likely_sponsor(name: str) -> bool:
    """Check if name looks like a sponsor/organization."""
    name_lower = name.lower()
    keywords = [
        'clinical', 'pharma', 'inc', 'llc', 'ltd', 'center', 'centre',
        'transparency', 'trials', 'research group', 'registry', 'gcr',
        'global', 'coordinator', 'gsk', 'glaxo', 'pfizer', 'novartis',
        'merck', 'sanofi', 'astrazeneca', 'roche', 'lilly', 'bristol',
        'johnson', 'abbvie', 'amgen', 'biogen', 'gilead', 'boehringer',
        'medical director', 'use central contact', 'contact',
        'biontech', 'responsible person', 'icd csd',
    ]
    return any(kw in name_lower for kw in keywords)


def main(args):
    print("🚀 OpenAlex PI Enrichment (V2 - Robust)")
    print(f"   Request delay: {REQUEST_DELAY}s")
    
    # Load subset investigator IDs
    ids_file = DATA_DIR / "subset_investigator_ids.json"
    if not ids_file.exists():
        print(f"❌ Error: {ids_file} not found!")
        sys.exit(1)
    
    with open(ids_file) as f:
        investigator_ids = json.load(f)
    
    print(f"\n📋 Loaded {len(investigator_ids):,} investigator IDs")
    
    if args.limit:
        investigator_ids = investigator_ids[:args.limit]
        print(f"   Limited to {len(investigator_ids):,}")
    
    # Get investigator details
    supabase = get_supabase_admin_client()
    
    print("\n📥 Fetching investigator details...")
    investigators = []
    batch_size = 500
    
    for i in range(0, len(investigator_ids), batch_size):
        batch_ids = investigator_ids[i:i + batch_size]
        result = supabase.table("investigators").select(
            "id, full_name, affiliation, orcid_id, s2_enriched_at"
        ).in_("id", batch_ids).execute()
        investigators.extend(result.data)
    
    print(f"   Fetched {len(investigators):,} investigators")
    
    # Filter
    original = len(investigators)
    investigators = [
        inv for inv in investigators
        if not is_likely_sponsor(inv["full_name"])
        and len(inv["full_name"]) > 5
        and not inv.get("s2_enriched_at")
    ]
    print(f"   Filtered: {original} → {len(investigators)}")
    
    if not investigators:
        print("\n✅ No investigators to process!")
        return
    
    # Estimate time
    est_min = len(investigators) * REQUEST_DELAY / 60
    print(f"\n⏱️  Estimated time: {est_min:.1f} minutes")
    
    # Process
    print(f"\n🔄 Starting enrichment...")
    
    matched = 0
    failed = 0
    batch_size = 50
    
    for i, inv in enumerate(investigators):
        # Progress
        if i % batch_size == 0 and i > 0:
            batch_num = i // batch_size
            total_batches = (len(investigators) + batch_size - 1) // batch_size
            rate = (matched / i * 100) if i > 0 else 0
            print(f"\n📊 Progress: {i}/{len(investigators)} ({rate:.1f}% match rate)")
            print(f"   Matched: {matched}, Failed: {failed}")
        
        # Search
        if args.verbose:
            print(f"  [{i+1}] Searching: {inv['full_name']}")
        
        result = search_author(inv["full_name"], inv.get("affiliation"))
        
        if args.verbose:
            print(f"       Result: {'FOUND' if result else 'NOT FOUND'}")
        
        if result:
            # Update database
            update_data = {
                "semantic_scholar_id": result["openalex_id"],
                "h_index": result["h_index"],
                "paper_count": result["paper_count"],
                "citation_count": result["citation_count"],
                "research_areas": result["research_areas"],
                "affiliations_s2": result["affiliations_openalex"],
                "s2_match_source": "openalex",
                "s2_enriched_at": datetime.now().isoformat(),
            }
            
            if result.get("orcid_id") and not inv.get("orcid_id"):
                update_data["orcid_id"] = result["orcid_id"]
            
            try:
                supabase.table("investigators").update(update_data).eq("id", inv["id"]).execute()
                matched += 1
            except Exception as e:
                print(f"    DB update error for {inv['full_name']}: {e}")
                failed += 1
        else:
            failed += 1
        
        # Rate limit
        time.sleep(REQUEST_DELAY)
    
    # Summary
    total = matched + failed
    rate = (matched / total * 100) if total > 0 else 0
    
    print(f"\n{'='*50}")
    print(f"✅ Enrichment complete!")
    print(f"   Total: {total:,}")
    print(f"   Matched: {matched:,} ({rate:.1f}%)")
    print(f"   Failed: {failed:,}")
    
    # Save results
    results = {
        "source": "openalex",
        "total_processed": total,
        "matched": matched,
        "match_rate": rate,
        "failed": failed,
        "timestamp": datetime.now().isoformat(),
    }
    with open(DATA_DIR / "enrichment_results.json", "w") as f:
        json.dump(results, f, indent=2)
    
    print(f"\n✅ Next: run 05_generate_embeddings.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, help="Limit investigators")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()
    main(args)
