#!/usr/bin/env python3
"""
Step 1: Fetch all trials from ClinicalTrials.gov that don't have PIs in our database.

Strategy:
1. Get all NCT IDs currently in our database (these have PIs)
2. Fetch ALL NCT IDs from ClinicalTrials.gov for our target conditions
3. The difference = trials we deleted (no PI in ClinicalTrials.gov data)
4. Save these NCT IDs for PI recovery via PubMed

This script uses the ClinicalTrials.gov API v2 to fetch trial NCT IDs.
"""

import os
import json
import time
import requests
from datetime import datetime
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# ClinicalTrials.gov API v2
CT_API_BASE = "https://clinicaltrials.gov/api/v2/studies"

# Output directory
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_existing_nct_ids() -> set[str]:
    """Get all NCT IDs currently in our database."""
    print("Fetching existing NCT IDs from database...")
    
    all_nct_ids = set()
    page_size = 1000  # Supabase default limit
    offset = 0
    max_iterations = 500  # Safety limit (500K trials max)
    iterations = 0
    
    while iterations < max_iterations:
        try:
            response = supabase.table("trials").select("nct_id").range(offset, offset + page_size - 1).execute()
            
            if not response.data:
                break
                
            for row in response.data:
                if row.get("nct_id"):
                    all_nct_ids.add(row["nct_id"])
            
            if len(all_nct_ids) % 10000 == 0 or len(response.data) < page_size:
                print(f"  Fetched {len(all_nct_ids)} NCT IDs so far...")
            
            if len(response.data) < page_size:
                break
                
            offset += page_size
            iterations += 1
            time.sleep(0.05)  # Rate limiting
        except Exception as e:
            print(f"  Error at offset {offset}: {e}")
            time.sleep(2)
            continue
    
    print(f"Total existing NCT IDs: {len(all_nct_ids)}")
    return all_nct_ids


def fetch_all_nct_ids_from_ctgov(condition: str = None, max_results: int = None) -> set[str]:
    """
    Fetch all NCT IDs from ClinicalTrials.gov.
    
    Args:
        condition: Optional condition filter (e.g., "diabetes", "obesity")
        max_results: Optional limit on results (for testing)
    
    Returns:
        Set of NCT IDs
    """
    print(f"Fetching NCT IDs from ClinicalTrials.gov...")
    if condition:
        print(f"  Filtering by condition: {condition}")
    
    all_nct_ids = set()
    page_token = None
    page_size = 1000  # Max allowed by API
    
    while True:
        params = {
            "format": "json",
            "fields": "NCTId",
            "pageSize": page_size,
        }
        
        if condition:
            params["query.cond"] = condition
        
        if page_token:
            params["pageToken"] = page_token
        
        try:
            response = requests.get(CT_API_BASE, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"  Error fetching from ClinicalTrials.gov: {e}")
            time.sleep(5)
            continue
        
        studies = data.get("studies", [])
        for study in studies:
            nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
            if nct_id:
                all_nct_ids.add(nct_id)
        
        print(f"  Fetched {len(all_nct_ids)} NCT IDs so far...")
        
        # Check if we've hit the limit
        if max_results and len(all_nct_ids) >= max_results:
            break
        
        # Get next page token
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        
        # Rate limiting
        time.sleep(0.1)
    
    print(f"Total NCT IDs from ClinicalTrials.gov: {len(all_nct_ids)}")
    return all_nct_ids


def fetch_trials_without_pi_from_ctgov() -> list[dict]:
    """
    Fetch trials from ClinicalTrials.gov that have no PI listed.
    
    ClinicalTrials.gov API allows filtering by whether contacts/investigators exist.
    We fetch trials and check if they have no investigators listed.
    """
    print("Fetching trials without investigators from ClinicalTrials.gov...")
    
    trials_without_pi = []
    page_token = None
    page_size = 1000
    
    while True:
        params = {
            "format": "json",
            "fields": "NCTId,BriefTitle,Condition,Phase,OverallStatus,ContactsLocationsModule",
            "pageSize": page_size,
        }
        
        if page_token:
            params["pageToken"] = page_token
        
        try:
            response = requests.get(CT_API_BASE, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"  Error: {e}")
            time.sleep(5)
            continue
        
        studies = data.get("studies", [])
        for study in studies:
            protocol = study.get("protocolSection", {})
            nct_id = protocol.get("identificationModule", {}).get("nctId")
            
            # Check if study has investigators
            contacts_module = protocol.get("contactsLocationsModule", {})
            overall_officials = contacts_module.get("overallOfficials", [])
            
            # If no investigators listed, this is a candidate for PI recovery
            if not overall_officials:
                trials_without_pi.append({
                    "nct_id": nct_id,
                    "title": protocol.get("identificationModule", {}).get("briefTitle"),
                    "conditions": protocol.get("conditionsModule", {}).get("conditions", []),
                    "phase": protocol.get("designModule", {}).get("phases", []),
                    "status": protocol.get("statusModule", {}).get("overallStatus"),
                })
        
        print(f"  Found {len(trials_without_pi)} trials without PI so far...")
        
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        
        time.sleep(0.1)
    
    return trials_without_pi


def main():
    """Main function to identify trials needing PI recovery."""
    
    print("=" * 60)
    print("PI Recovery - Step 1: Identify Trials Without PIs")
    print("=" * 60)
    print()
    
    # Option 1: Compare our DB with ClinicalTrials.gov
    # This finds trials we deleted
    existing_nct_ids = get_existing_nct_ids()
    
    print()
    print("Fetching a sample of trials without investigators from ClinicalTrials.gov...")
    print("(This will help us understand the scope)")
    print()
    
    # Fetch trials without PI from ClinicalTrials.gov (sample)
    # For full recovery, we'd need to paginate through all ~500K+ trials
    trials_without_pi = []
    page_token = None
    max_pages = 200  # ~200K trials sample
    pages_fetched = 0
    
    while pages_fetched < max_pages:
        params = {
            "format": "json",
            "fields": "NCTId,BriefTitle,OverallStatus",
            "pageSize": 1000,
        }
        
        if page_token:
            params["pageToken"] = page_token
        
        try:
            response = requests.get(CT_API_BASE, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as e:
            print(f"  Error: {e}")
            time.sleep(5)
            continue
        
        studies = data.get("studies", [])
        for study in studies:
            protocol = study.get("protocolSection", {})
            nct_id = protocol.get("identificationModule", {}).get("nctId")
            
            # Check if this trial is NOT in our database
            if nct_id and nct_id not in existing_nct_ids:
                trials_without_pi.append({
                    "nct_id": nct_id,
                    "title": protocol.get("identificationModule", {}).get("briefTitle"),
                    "status": protocol.get("statusModule", {}).get("overallStatus"),
                })
        
        pages_fetched += 1
        if pages_fetched % 10 == 0:
            print(f"  Processed {pages_fetched} pages, found {len(trials_without_pi)} missing trials...")
        
        page_token = data.get("nextPageToken")
        if not page_token:
            break
        
        time.sleep(0.05)
    
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Trials in our database: {len(existing_nct_ids)}")
    print(f"Trials missing from our database (sample): {len(trials_without_pi)}")
    print()
    
    # Save the missing NCT IDs
    output_file = os.path.join(OUTPUT_DIR, "trials_to_recover.json")
    with open(output_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "existing_count": len(existing_nct_ids),
            "missing_count": len(trials_without_pi),
            "trials": trials_without_pi[:10000],  # Save first 10K for now
        }, f, indent=2)
    
    print(f"Saved missing trials to: {output_file}")
    print()
    print("Next step: Run 02_search_pubmed.py to find PIs for these trials")


if __name__ == "__main__":
    main()
