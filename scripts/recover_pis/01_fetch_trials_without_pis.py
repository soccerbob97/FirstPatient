#!/usr/bin/env python3
"""
Step 1: Fetch all trials that are missing PI information.

These are trials with avoid_search=true, meaning they were imported
without principal investigator data from ClinicalTrials.gov.

Output: CSV file with NCT IDs and trial metadata for PI recovery.
"""

import os
import csv
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# Config
OUTPUT_FILE = "trials_without_pis.csv"
BATCH_SIZE = 1000


def get_supabase_client():
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")
    return create_client(url, key)


def fetch_trials_without_pis():
    """Fetch all trials with avoid_search=true (no PI data)."""
    client = get_supabase_client()
    
    # Get total count
    count_result = client.table("trials").select("id", count="exact").eq("avoid_search", True).limit(1).execute()
    total = count_result.count
    print(f"Total trials without PIs: {total:,}")
    
    # Fetch in batches
    all_trials = []
    offset = 0
    
    while offset < total:
        result = client.table("trials").select(
            "id, nct_id, brief_title, conditions, phase, overall_status, lead_sponsor_name, start_date"
        ).eq("avoid_search", True).range(offset, offset + BATCH_SIZE - 1).execute()
        
        all_trials.extend(result.data)
        offset += BATCH_SIZE
        print(f"  Fetched {len(all_trials):,} / {total:,} trials...")
    
    return all_trials


def save_to_csv(trials, filename):
    """Save trials to CSV for processing."""
    if not trials:
        print("No trials to save.")
        return
    
    fieldnames = ["nct_id", "brief_title", "conditions", "phase", "overall_status", "lead_sponsor_name", "start_date"]
    
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for trial in trials:
            # Convert conditions array to string
            if trial.get("conditions"):
                trial["conditions"] = "; ".join(trial["conditions"]) if isinstance(trial["conditions"], list) else trial["conditions"]
            writer.writerow(trial)
    
    print(f"Saved {len(trials):,} trials to {filename}")


def main():
    print(f"=== Fetching Trials Without PIs ===")
    print(f"Started: {datetime.now().isoformat()}")
    print()
    
    trials = fetch_trials_without_pis()
    save_to_csv(trials, OUTPUT_FILE)
    
    print()
    print(f"Completed: {datetime.now().isoformat()}")
    print(f"Next step: Run 02_search_pubmed.py to find PIs from publications")


if __name__ == "__main__":
    main()
