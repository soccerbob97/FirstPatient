#!/usr/bin/env python3
"""
Step 2: Get Subset Trials

Filters trials by condition (diabetes, breast cancer, obesity) and 
gets the linked investigators for enrichment.

Outputs:
- subset_trial_ids.json: List of trial IDs in subset
- subset_investigator_ids.json: List of investigator IDs to enrich

Usage:
    PYTHONPATH=. python scripts/v2_test/02_get_subset_trials.py
"""

import os
import sys
import json
from pathlib import Path

from dotenv import load_dotenv
import requests

load_dotenv()

# Output directory
OUTPUT_DIR = Path(__file__).parent / "data"

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
        }
    
    def query(self, table: str, select: str = "*", limit: int = None) -> list[dict]:
        url = f"{self.url}/rest/v1/{table}?select={select}"
        if limit:
            url += f"&limit={limit}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def query_ilike(self, table: str, select: str, column: str, pattern: str, limit: int = 10000) -> list[dict]:
        url = f"{self.url}/rest/v1/{table}?select={select}&{column}=ilike.{pattern}&limit={limit}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def query_in(self, table: str, select: str, column: str, values: list, limit: int = 10000) -> list[dict]:
        values_str = ",".join(str(v) for v in values)
        url = f"{self.url}/rest/v1/{table}?select={select}&{column}=in.({values_str})&limit={limit}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()
    
    def query_is_null(self, table: str, select: str, column: str, limit: int = 10000) -> list[dict]:
        url = f"{self.url}/rest/v1/{table}?select={select}&{column}=is.null&limit={limit}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()


def get_supabase_client():
    return SimpleSupabaseClient(SUPABASE_URL, SUPABASE_KEY)

# Condition keywords for filtering
CONDITION_KEYWORDS = {
    "diabetes": [
        "%diabetes%", "%diabetic%", "%t1d%", "%t2d%", 
        "%insulin%", "%glycemic%", "%hba1c%", "%glucose%"
    ],
    "breast_cancer": [
        "%breast cancer%", "%breast neoplasm%", "%breast tumor%", 
        "%mammary%", "%mastectomy%", "%brca%"
    ],
    "obesity": [
        "%obesity%", "%obese%", "%overweight%", 
        "%weight loss%", "%bariatric%", "%adipos%"
    ]
}


def get_subset_trials(client) -> list[int]:
    """Get trial IDs matching our condition keywords."""
    print("\n📋 Fetching subset trials...")
    
    all_trial_ids = set()
    
    for condition, keywords in CONDITION_KEYWORDS.items():
        print(f"\n   Searching for {condition}...")
        
        for keyword in keywords:
            try:
                result = client.query_ilike("trials", "id", "brief_title", keyword)
                ids = [r["id"] for r in result]
                all_trial_ids.update(ids)
                
                if ids:
                    print(f"      '{keyword}' in title: {len(ids)} trials")
            except Exception as e:
                print(f"      Error searching '{keyword}': {e}")
    
    trial_ids = sorted(list(all_trial_ids))
    print(f"\n   ✅ Total unique trials: {len(trial_ids)}")
    
    return trial_ids


def get_linked_investigators(client, trial_ids: list[int]) -> list[int]:
    """Get investigator IDs linked to the subset trials."""
    print("\n👥 Fetching linked investigators...")
    
    all_investigator_ids = set()
    batch_size = 500
    
    for i in range(0, len(trial_ids), batch_size):
        batch = trial_ids[i:i + batch_size]
        
        try:
            result = client.query_in("trial_investigators", "investigator_id", "trial_id", batch)
            ids = [r["investigator_id"] for r in result]
            all_investigator_ids.update(ids)
            
            print(f"   Batch {i//batch_size + 1}: {len(ids)} investigators")
        except Exception as e:
            print(f"   Error in batch {i//batch_size + 1}: {e}")
    
    investigator_ids = sorted(list(all_investigator_ids))
    print(f"\n   ✅ Total unique investigators: {len(investigator_ids)}")
    
    return investigator_ids


def get_unenriched_investigators(client, investigator_ids: list[int]) -> list[int]:
    """Filter to only investigators not yet enriched."""
    print("\n🔍 Filtering to unenriched investigators...")
    
    # Return all - filtering will happen during enrichment
    print(f"   ✅ Returning all {len(investigator_ids)} investigators (will filter during enrichment)")
    return investigator_ids


def main():
    print("🚀 Getting subset trials and investigators...")
    print("   Conditions: Diabetes, Breast Cancer, Obesity")
    
    # Create output directory
    OUTPUT_DIR.mkdir(exist_ok=True)
    
    client = get_supabase_client()
    
    # Step 1: Get subset trials
    trial_ids = get_subset_trials(client)
    
    # Save trial IDs
    trial_ids_file = OUTPUT_DIR / "subset_trial_ids.json"
    with open(trial_ids_file, "w") as f:
        json.dump(trial_ids, f)
    print(f"\n💾 Saved {len(trial_ids)} trial IDs to {trial_ids_file}")
    
    # Step 2: Get linked investigators
    investigator_ids = get_linked_investigators(client, trial_ids)
    
    # Step 3: Filter to unenriched only
    unenriched_ids = get_unenriched_investigators(client, investigator_ids)
    
    # Save investigator IDs
    inv_ids_file = OUTPUT_DIR / "subset_investigator_ids.json"
    with open(inv_ids_file, "w") as f:
        json.dump(unenriched_ids, f)
    print(f"💾 Saved {len(unenriched_ids)} investigator IDs to {inv_ids_file}")
    
    # Summary
    print("\n" + "="*50)
    print("📊 Summary")
    print("="*50)
    print(f"   Subset trials: {len(trial_ids):,}")
    print(f"   Linked investigators: {len(investigator_ids):,}")
    print(f"   To enrich: {len(unenriched_ids):,}")
    print("\n✅ Complete! Next: run 03_enrich_subset_pis.py")


if __name__ == "__main__":
    main()
