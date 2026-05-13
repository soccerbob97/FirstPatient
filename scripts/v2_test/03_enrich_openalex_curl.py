#!/usr/bin/env python3
"""
Step 3: Enrich Subset PIs with OpenAlex (using curl)

Uses subprocess + curl instead of requests library to avoid hanging issues.

Usage:
    PYTHONPATH=. python scripts/v2_test/03_enrich_openalex_curl.py
    PYTHONPATH=. python scripts/v2_test/03_enrich_openalex_curl.py --limit 100
"""

import os
import sys
import json
import subprocess
import argparse
import urllib.parse
from pathlib import Path
from datetime import datetime
from typing import Optional
import time

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.db.supabase_client import get_supabase_admin_client

DATA_DIR = Path(__file__).parent / "data"
OPENALEX_BASE_URL = "https://api.openalex.org"
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "")
REQUEST_DELAY = 0.12  # 120ms between requests (~8/sec with API key)


def clean_name(name: str) -> str:
    """Remove titles and clean name for search."""
    # Multi-word titles first (order matters)
    multi_word_titles = [
        "Associate Professor", "Assistant Professor", "A. Professor",
        "Medical Director", "Principal Investigator", "Assoc. Prof.",
        "Asst. Prof.", "Prof. Dr.", "Master in Physiotherapy",
        "Master in physiotherapy",
    ]
    
    # Single word titles
    single_titles = [
        "MD", "M.D.", "PhD", "Ph.D.", "Dr.", "Dr", "Prof.", "Prof", "Professor",
        "DO", "D.O.", "MPH", "M.P.H.", "MS", "M.S.", "MSc", "M.Sc.", "Msc",
        "MBA", "M.B.A.", "RN", "R.N.", "BSN", "B.S.N.", "DNP", "D.N.P.",
        "FACS", "FACP", "FACR", "FAHA", "FCCP", "FRCP", "FRS",
        "Jr.", "Jr", "Sr.", "Sr", "III", "II", "IV",
        "MBChB", "MBBS", "MBBCh", "MRCP", "FRCS", "RD", "DDS", "Phd", "PHD",
        "PI", "Associate", "Assistant", "Assoc", "Asst",
    ]
    
    result = name
    
    # Remove multi-word titles first
    for title in multi_word_titles:
        result = result.replace(f", {title}", "")
        result = result.replace(f" {title}", "")
        result = result.replace(title, "")
    
    # Then single titles
    for title in single_titles:
        result = result.replace(f", {title}", "")
        result = result.replace(f" {title}", "")
        result = result.replace(f"{title},", "")
        result = result.replace(f"{title} ", "")
    
    result = " ".join(result.split())
    result = result.strip(" ,.")
    return result


def search_author_curl(name: str, retry_count: int = 0) -> Optional[dict]:
    """Search for an author using curl subprocess."""
    if retry_count > 3:
        return None
    
    clean = clean_name(name)
    if not clean or len(clean) < 3:
        return None
    
    # Build URL with encoded search param and API key
    encoded_name = urllib.parse.quote(clean)
    url = f"{OPENALEX_BASE_URL}/authors?search={encoded_name}&per_page=5"
    if OPENALEX_API_KEY:
        url += f"&api_key={OPENALEX_API_KEY}"
    
    try:
        result = subprocess.run(
            ["curl", "-s", "-m", "5", "--connect-timeout", "3", url],
            capture_output=True,
            text=True,
            timeout=8
        )
        
        if result.returncode != 0:
            return None
        
        data = json.loads(result.stdout)
        
        # Check for rate limit error
        if "error" in data:
            if "Rate limit" in str(data.get("error", "")):
                time.sleep(5)
                return search_author_curl(name, retry_count + 1)
            return None
        
        results = data.get("results", [])
        if not results:
            return None
        
        # Get top result with works
        top = results[0]
        if top.get("works_count", 0) <= 0:
            return None
        
        # Extract data
        stats = top.get("summary_stats", {})
        
        topics = []
        for topic in top.get("topics", [])[:5]:
            if topic.get("display_name"):
                topics.append(topic["display_name"])
        
        affiliations = []
        for aff in top.get("affiliations", [])[:3]:
            inst = aff.get("institution", {})
            if inst.get("display_name"):
                affiliations.append(inst["display_name"])
        
        orcid = None
        if top.get("orcid"):
            orcid = top["orcid"].split("/")[-1]
        
        return {
            "openalex_id": top.get("id", "").replace("https://openalex.org/", ""),
            "h_index": stats.get("h_index"),
            "paper_count": top.get("works_count"),
            "citation_count": top.get("cited_by_count"),
            "research_areas": topics,
            "affiliations_openalex": affiliations,
            "orcid_id": orcid,
        }
        
    except subprocess.TimeoutExpired:
        time.sleep(2)
        return search_author_curl(name, retry_count + 1)
    except json.JSONDecodeError:
        return None
    except Exception as e:
        print(f"    Error: {e}")
        return None


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
    print("🚀 OpenAlex PI Enrichment (curl version)")
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
    print(f"   Filtered: {original} → {len(investigators)} (skipped sponsors/already enriched)")
    
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
    progress_interval = 50
    
    for i, inv in enumerate(investigators):
        # Progress update
        if i > 0 and i % progress_interval == 0:
            rate = (matched / i * 100) if i > 0 else 0
            print(f"\n📊 Progress: {i}/{len(investigators)} ({rate:.1f}% match rate)")
            print(f"   Matched: {matched}, Failed: {failed}")
        
        # Search using curl
        if args.verbose:
            print(f"  [{i+1}] {inv['full_name'][:40]}...", end=" ")
        
        result = search_author_curl(inv["full_name"])
        
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
                if args.verbose:
                    print(f"✓ h={result['h_index']}")
            except Exception as e:
                print(f"    DB error: {e}")
                failed += 1
        else:
            failed += 1
            if args.verbose:
                print("✗")
        
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
        "source": "openalex_curl",
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
