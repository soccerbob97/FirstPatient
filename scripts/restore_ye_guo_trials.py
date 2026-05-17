#!/usr/bin/env python3
"""
Script to restore Ye Guo trial connections from ctg-studies_full.json

Usage:
  Step 1: Parse JSON and save locally
    python scripts/restore_ye_guo_trials.py parse
  
  Step 2: Insert connections to database
    python scripts/restore_ye_guo_trials.py insert
"""
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

YE_GUO_INVESTIGATOR_ID = 132342
LOCAL_CACHE_FILE = "scripts/ye_guo_trials_cache.json"


def step1_parse_json(json_file: str):
    """
    Step 1: Parse the large JSON file and save NCT IDs locally.
    """
    nct_ids = []
    
    print(f"Step 1: Scanning {json_file} for Ye Guo trials...")
    
    with open(json_file, 'r', encoding='utf-8') as f:
        current_nct_id = None
        
        for line_num, line in enumerate(f):
            # Find NCT IDs
            nct_matches = re.findall(r'"nctId":"(NCT\d+)"', line)
            if nct_matches:
                current_nct_id = nct_matches[-1]
            
            # Check if Ye Guo is mentioned
            if re.search(r'Ye\s+Guo', line, re.IGNORECASE):
                if current_nct_id and current_nct_id not in nct_ids:
                    nct_ids.append(current_nct_id)
                    print(f"  Found: {current_nct_id}")
            
            if line_num % 100000 == 0 and line_num > 0:
                print(f"  Processed {line_num} lines, found {len(nct_ids)} trials...")
    
    # Save to local cache file
    cache_data = {
        "investigator_id": YE_GUO_INVESTIGATOR_ID,
        "investigator_name": "Ye Guo",
        "nct_ids": nct_ids,
        "total_found": len(nct_ids)
    }
    
    with open(LOCAL_CACHE_FILE, 'w') as f:
        json.dump(cache_data, f, indent=2)
    
    print(f"\n=== Step 1 Complete ===")
    print(f"Found {len(nct_ids)} trials mentioning Ye Guo")
    print(f"Saved to: {LOCAL_CACHE_FILE}")
    print(f"\nRun 'python scripts/restore_ye_guo_trials.py insert' to add to database")


def step2_insert_connections():
    """
    Step 2: Read from local cache and insert connections to database.
    """
    from src.db.supabase_client import get_supabase_admin_client
    
    # Load from cache
    if not os.path.exists(LOCAL_CACHE_FILE):
        print(f"Error: Cache file not found: {LOCAL_CACHE_FILE}")
        print("Run 'python scripts/restore_ye_guo_trials.py parse' first")
        sys.exit(1)
    
    with open(LOCAL_CACHE_FILE, 'r') as f:
        cache_data = json.load(f)
    
    nct_ids = cache_data["nct_ids"]
    investigator_id = cache_data["investigator_id"]
    
    print(f"Step 2: Inserting {len(nct_ids)} trial connections for {cache_data['investigator_name']}...")
    
    client = get_supabase_admin_client()
    
    added = 0
    skipped = 0
    not_found = 0
    errors = []
    
    for i, nct_id in enumerate(nct_ids):
        # Find trial in database
        result = client.table("trials").select("id").eq("nct_id", nct_id).limit(1).execute()
        
        if not result.data:
            print(f"  [{i+1}/{len(nct_ids)}] {nct_id} - NOT FOUND in database")
            not_found += 1
            continue
        
        trial_id = result.data[0]["id"]
        
        # Check if connection already exists
        existing = client.table("trial_investigators").select("id").eq(
            "trial_id", trial_id
        ).eq("investigator_id", investigator_id).limit(1).execute()
        
        if existing.data:
            print(f"  [{i+1}/{len(nct_ids)}] {nct_id} (trial_id={trial_id}) - already connected")
            skipped += 1
            continue
        
        # Add the connection
        try:
            client.table("trial_investigators").insert({
                "trial_id": trial_id,
                "investigator_id": investigator_id,
                "role": "Principal Investigator"
            })
            print(f"  [{i+1}/{len(nct_ids)}] {nct_id} (trial_id={trial_id}) - ADDED")
            added += 1
        except Exception as e:
            print(f"  [{i+1}/{len(nct_ids)}] {nct_id} (trial_id={trial_id}) - ERROR: {e}")
            errors.append({"nct_id": nct_id, "trial_id": trial_id, "error": str(e)})
    
    print(f"\n=== Step 2 Complete ===")
    print(f"Added: {added}")
    print(f"Skipped (already exists): {skipped}")
    print(f"Not found in database: {not_found}")
    print(f"Errors: {len(errors)}")
    print(f"Total processed: {len(nct_ids)}")
    
    # Save results
    results = {
        "added": added,
        "skipped": skipped,
        "not_found": not_found,
        "errors": errors
    }
    
    results_file = "scripts/ye_guo_restore_results.json"
    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {results_file}")


def show_usage():
    print(__doc__)
    print("Commands:")
    print("  parse  - Step 1: Parse JSON file and save NCT IDs locally")
    print("  insert - Step 2: Insert trial connections to database")
    print("  status - Show current status")


def show_status():
    """Show current status of Ye Guo trials."""
    from src.db.supabase_client import get_supabase_admin_client
    
    client = get_supabase_admin_client()
    result = client.table("trial_investigators").select("id", count="exact").eq(
        "investigator_id", YE_GUO_INVESTIGATOR_ID
    ).limit(1).execute()
    
    print(f"Ye Guo (ID {YE_GUO_INVESTIGATOR_ID}) current trial count: {result.count}")
    
    if os.path.exists(LOCAL_CACHE_FILE):
        with open(LOCAL_CACHE_FILE, 'r') as f:
            cache = json.load(f)
        print(f"Cache file exists: {cache['total_found']} NCT IDs found")
    else:
        print("Cache file not found - run 'parse' first")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        show_usage()
        sys.exit(1)
    
    command = sys.argv[1].lower()
    
    if command == "parse":
        json_file = "ctg-studies_full.json"
        if not os.path.exists(json_file):
            print(f"Error: {json_file} not found")
            sys.exit(1)
        step1_parse_json(json_file)
    
    elif command == "insert":
        step2_insert_connections()
    
    elif command == "status":
        show_status()
    
    else:
        print(f"Unknown command: {command}")
        show_usage()
        sys.exit(1)
