#!/usr/bin/env python3
"""
Step 4: Import recovered PI data back into the database.

This script:
1. Loads recovered PIs from PubMed and ClinicalTrials.gov
2. Re-fetches full trial data from ClinicalTrials.gov
3. Creates/updates investigators, sites, and trials in the database
4. Links everything together

IMPORTANT: This will add new trials to the database. Make sure you have
run the previous steps and reviewed the recovered PI data.
"""

import os
import json
import time
from datetime import datetime
from typing import Optional
import requests
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


def fetch_full_trial_data(nct_id: str) -> Optional[dict]:
    """Fetch complete trial data from ClinicalTrials.gov."""
    url = f"{CT_API_BASE}/{nct_id}"
    params = {"format": "json"}
    
    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 404:
            return None
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"    Error fetching {nct_id}: {e}")
        return None


def get_or_create_investigator(pi_data: dict) -> Optional[int]:
    """Get existing investigator or create new one."""
    pi_name = pi_data.get("pi_name")
    if not pi_name:
        return None
    
    # Check if investigator exists
    response = supabase.table("investigators").select("id").eq("full_name", pi_name).limit(1).execute()
    
    if response.data:
        return response.data[0]["id"]
    
    # Create new investigator
    new_investigator = {
        "full_name": pi_name,
        "first_name": pi_data.get("pi_first_name"),
        "last_name": pi_data.get("pi_last_name"),
        "created_at": datetime.now().isoformat(),
    }
    
    response = supabase.table("investigators").insert(new_investigator).execute()
    
    if response.data:
        return response.data[0]["id"]
    
    return None


def get_or_create_site(affiliation: str) -> Optional[int]:
    """Get existing site or create new one based on affiliation."""
    if not affiliation:
        return None
    
    # Check if site exists (fuzzy match on name)
    response = supabase.table("sites").select("id").ilike("name", f"%{affiliation[:50]}%").limit(1).execute()
    
    if response.data:
        return response.data[0]["id"]
    
    # Create new site
    new_site = {
        "name": affiliation[:255],
        "created_at": datetime.now().isoformat(),
    }
    
    response = supabase.table("sites").insert(new_site).execute()
    
    if response.data:
        return response.data[0]["id"]
    
    return None


def create_trial(trial_data: dict, nct_id: str) -> Optional[int]:
    """Create a new trial in the database."""
    protocol = trial_data.get("protocolSection", {})
    
    # Extract trial info
    id_module = protocol.get("identificationModule", {})
    status_module = protocol.get("statusModule", {})
    design_module = protocol.get("designModule", {})
    conditions_module = protocol.get("conditionsModule", {})
    description_module = protocol.get("descriptionModule", {})
    
    # Check if trial already exists
    response = supabase.table("trials").select("id").eq("nct_id", nct_id).limit(1).execute()
    if response.data:
        return response.data[0]["id"]
    
    # Build trial record
    new_trial = {
        "nct_id": nct_id,
        "brief_title": id_module.get("briefTitle"),
        "official_title": id_module.get("officialTitle"),
        "brief_summary": description_module.get("briefSummary"),
        "overall_status": status_module.get("overallStatus"),
        "phase": ", ".join(design_module.get("phases", [])) or None,
        "conditions": conditions_module.get("conditions", []),
        "start_date": status_module.get("startDateStruct", {}).get("date"),
        "completion_date": status_module.get("completionDateStruct", {}).get("date"),
        "created_at": datetime.now().isoformat(),
    }
    
    response = supabase.table("trials").insert(new_trial).execute()
    
    if response.data:
        return response.data[0]["id"]
    
    return None


def link_investigator_to_trial(investigator_id: int, trial_id: int, site_id: Optional[int], role: str = "PRINCIPAL_INVESTIGATOR"):
    """Create investigator_sites link."""
    # Check if link exists
    query = supabase.table("investigator_sites").select("id").eq("investigator_id", investigator_id).eq("trial_id", trial_id)
    
    response = query.limit(1).execute()
    if response.data:
        return  # Already linked
    
    # Create link
    new_link = {
        "investigator_id": investigator_id,
        "trial_id": trial_id,
        "site_id": site_id,
        "role": role,
        "created_at": datetime.now().isoformat(),
    }
    
    supabase.table("investigator_sites").insert(new_link).execute()


def import_recovered_pi(pi_data: dict) -> bool:
    """Import a single recovered PI and their trial."""
    nct_id = pi_data.get("nct_id")
    
    # Fetch full trial data
    trial_data = fetch_full_trial_data(nct_id)
    if not trial_data:
        print(f"    Could not fetch trial data for {nct_id}")
        return False
    
    # Create/get investigator
    investigator_id = get_or_create_investigator(pi_data)
    if not investigator_id:
        print(f"    Could not create investigator for {nct_id}")
        return False
    
    # Create/get site (if affiliation available)
    site_id = get_or_create_site(pi_data.get("pi_affiliation"))
    
    # Create trial
    trial_id = create_trial(trial_data, nct_id)
    if not trial_id:
        print(f"    Could not create trial for {nct_id}")
        return False
    
    # Link investigator to trial
    role = pi_data.get("pi_role", "PRINCIPAL_INVESTIGATOR")
    link_investigator_to_trial(investigator_id, trial_id, site_id, role)
    
    return True


def main():
    """Main function to import recovered PIs."""
    
    print("=" * 60)
    print("PI Recovery - Step 4: Import Recovered PIs to Database")
    print("=" * 60)
    print()
    
    # Load recovered PIs from both sources
    all_pis = []
    
    pubmed_file = os.path.join(OUTPUT_DIR, "recovered_pis_pubmed.json")
    if os.path.exists(pubmed_file):
        with open(pubmed_file) as f:
            data = json.load(f)
            all_pis.extend(data.get("pis", []))
        print(f"Loaded {len(data.get('pis', []))} PIs from PubMed")
    
    ctgov_file = os.path.join(OUTPUT_DIR, "recovered_pis_ctgov.json")
    if os.path.exists(ctgov_file):
        with open(ctgov_file) as f:
            data = json.load(f)
            all_pis.extend(data.get("pis", []))
        print(f"Loaded {len(data.get('pis', []))} PIs from ClinicalTrials.gov")
    
    if not all_pis:
        print("No recovered PIs found. Run steps 2 and 3 first.")
        return
    
    # Deduplicate by NCT ID
    seen_nct_ids = set()
    unique_pis = []
    for pi in all_pis:
        nct_id = pi.get("nct_id")
        if nct_id and nct_id not in seen_nct_ids:
            seen_nct_ids.add(nct_id)
            unique_pis.append(pi)
    
    print(f"Total unique trials to import: {len(unique_pis)}")
    print()
    
    # Confirm before proceeding
    print("This will add new trials and investigators to the database.")
    response = input("Continue? (y/n): ")
    if response.lower() != "y":
        print("Aborted.")
        return
    
    print()
    
    # Import each PI
    success_count = 0
    error_count = 0
    
    for i, pi_data in enumerate(unique_pis):
        nct_id = pi_data.get("nct_id")
        
        if (i + 1) % 50 == 0:
            print(f"Progress: {i + 1}/{len(unique_pis)} ({success_count} imported)")
        
        try:
            if import_recovered_pi(pi_data):
                success_count += 1
                print(f"  ✓ {nct_id}: {pi_data.get('pi_name')}")
            else:
                error_count += 1
        except Exception as e:
            print(f"  ✗ {nct_id}: {e}")
            error_count += 1
        
        # Rate limiting
        time.sleep(0.2)
    
    print()
    print("=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    print(f"Successfully imported: {success_count}")
    print(f"Errors: {error_count}")
    print()
    print("Next steps:")
    print("1. Generate embeddings for new trials")
    print("2. Enrich new investigators with OpenAlex")
    print("3. Rebuild HNSW index if needed")


if __name__ == "__main__":
    main()
