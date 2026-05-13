#!/usr/bin/env python3
"""
Step 6: Test Search

Tests the V2 search with enriched data and compares to V1.

Usage:
    PYTHONPATH=. python scripts/v2_test/06_test_search.py
"""

import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.db.supabase_client import get_supabase_admin_client

# Voyage API configuration
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
VOYAGE_MODEL = "voyage-3.5-lite"
VOYAGE_DIMENSIONS = 1024

# Test queries
TEST_QUERIES = [
    "Find experienced oncology PI in Germany",
    "Diabetes clinical trial with academic medical center",
    "Breast cancer immunotherapy trial",
    "Obesity treatment with bariatric surgery",
    "Phase 3 diabetes trial with insulin",
    "Find PI with high h-index for cancer research",
]


def generate_query_embedding(query: str) -> list[float]:
    """Generate embedding for a search query using Voyage."""
    try:
        import voyageai
    except ImportError:
        print("❌ voyageai not installed. Run: pip install voyageai")
        sys.exit(1)
    
    client = voyageai.Client(api_key=VOYAGE_API_KEY)
    
    result = client.embed(
        [query],
        model=VOYAGE_MODEL,
        input_type="query",
        output_dimension=VOYAGE_DIMENSIONS
    )
    
    return result.embeddings[0]


def search_v2(supabase, query: str, limit: int = 5) -> list[dict]:
    """Search using V2 test embeddings."""
    # Generate query embedding
    query_embedding = generate_query_embedding(query)
    
    # Call the test search function
    result = supabase.rpc(
        "search_trials_v2_test",
        {
            "query_embedding": query_embedding,
            "match_threshold": 0.3,
            "match_count": limit
        }
    ).execute()
    
    return result.data


def get_trial_details(supabase, trial_id: int) -> dict:
    """Get enriched trial details including PI and site info."""
    # Get trial
    trial = supabase.table("trials").select(
        "nct_id, brief_title, conditions, phase"
    ).eq("id", trial_id).single().execute()
    
    details = trial.data
    
    # Get lead PI with enriched data
    try:
        pi_link = supabase.table("trial_investigators").select(
            "investigator_id"
        ).eq("trial_id", trial_id).eq("role", "PRINCIPAL_INVESTIGATOR").limit(1).execute()
        
        if pi_link.data:
            pi = supabase.table("investigators").select(
                "full_name, h_index, total_trials, therapeutic_areas, s2_match_source"
            ).eq("id", pi_link.data[0]["investigator_id"]).single().execute()
            
            details["lead_pi"] = pi.data
    except:
        details["lead_pi"] = None
    
    # Get lead site
    try:
        site_link = supabase.table("trial_sites").select(
            "site_id"
        ).eq("trial_id", trial_id).limit(1).execute()
        
        if site_link.data:
            site = supabase.table("sites").select(
                "facility_name, city, country"
            ).eq("id", site_link.data[0]["site_id"]).single().execute()
            
            details["lead_site"] = site.data
    except:
        details["lead_site"] = None
    
    return details


def print_result(i: int, result: dict, details: dict):
    """Pretty print a search result."""
    print(f"\n   {i+1}. {details.get('brief_title', 'N/A')[:60]}...")
    print(f"      NCT ID: {details.get('nct_id')}")
    print(f"      Phase: {details.get('phase')}")
    print(f"      Similarity: {result.get('similarity', 0):.3f}")
    
    if details.get("lead_pi"):
        pi = details["lead_pi"]
        print(f"      Lead PI: {pi.get('full_name')}")
        if pi.get("h_index"):
            print(f"         h-index: {pi['h_index']}, trials: {pi.get('total_trials', 'N/A')}")
        if pi.get("therapeutic_areas"):
            print(f"         Areas: {', '.join(pi['therapeutic_areas'][:3])}")
        if pi.get("s2_match_source"):
            print(f"         Match: {pi['s2_match_source']}")
    
    if details.get("lead_site"):
        site = details["lead_site"]
        print(f"      Site: {site.get('facility_name', 'N/A')[:40]}, {site.get('country')}")


def main():
    print("🔍 Testing V2 Search with Enriched Data")
    print("="*60)
    
    if not VOYAGE_API_KEY:
        print("❌ VOYAGE_API_KEY not found in .env")
        return
    
    supabase = get_supabase_admin_client()
    
    # Check if test table has data
    count_result = supabase.table("trials_embeddings_v2_test").select(
        "id", count="exact"
    ).limit(1).execute()
    
    embedding_count = count_result.count if hasattr(count_result, 'count') else len(count_result.data)
    print(f"\n📊 Test embeddings available: {embedding_count}")
    
    if embedding_count == 0:
        print("❌ No embeddings in test table. Run 05_generate_embeddings.py first.")
        return
    
    # Run test queries
    for query in TEST_QUERIES:
        print(f"\n{'='*60}")
        print(f"🔎 Query: \"{query}\"")
        print("-"*60)
        
        try:
            results = search_v2(supabase, query, limit=3)
            
            if not results:
                print("   No results found")
                continue
            
            for i, result in enumerate(results):
                details = get_trial_details(supabase, result["trial_id"])
                print_result(i, result, details)
                
        except Exception as e:
            print(f"   ❌ Error: {e}")
    
    print(f"\n{'='*60}")
    print("✅ Search testing complete!")
    print("\nNext steps:")
    print("  1. Review results above")
    print("  2. Compare with production search quality")
    print("  3. If satisfied, proceed to Phase B (production rollout)")


if __name__ == "__main__":
    main()
