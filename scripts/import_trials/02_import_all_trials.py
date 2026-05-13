#!/usr/bin/env python3
"""
Import ALL trials from ctg-studies_full.json to Supabase.

This script:
1. Streams through the 9GB JSON file
2. Imports ALL trials, investigators, sites, and relationships
3. Sets avoid_search=true for trials WITHOUT investigators
4. Saves progress for resume capability

Usage:
    python scripts/import_trials/02_import_all_trials.py
"""

import os
import json
import ijson
import re
import time
from datetime import datetime
from typing import Optional
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# Supabase connection
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# Input file
CTG_FILE = "/Users/harshakaranth/Harsha/Projects/ClinicalTrialProject/ctg-studies_full.json"

# Output directory for logs
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Progress save interval
SAVE_INTERVAL = 500


def normalize_name(name: str) -> str:
    """Normalize a name for matching."""
    if not name:
        return ""
    return re.sub(r'[^a-z0-9\s]', '', name.lower()).strip()


def has_investigator(study: dict) -> bool:
    """Check if a study has investigator information."""
    protocol = study.get("protocolSection", {})
    
    # Check overallOfficials
    contacts_module = protocol.get("contactsLocationsModule", {})
    overall_officials = contacts_module.get("overallOfficials", [])
    
    for official in overall_officials:
        name = official.get("name", "")
        role = official.get("role", "")
        if name and role in ["PRINCIPAL_INVESTIGATOR", "STUDY_DIRECTOR"]:
            return True
    
    # Check responsibleParty
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    responsible_party = sponsor_module.get("responsibleParty", {})
    
    if responsible_party.get("investigatorFullName"):
        return True
    
    # Check any official with a name
    for official in overall_officials:
        if official.get("name"):
            return True
    
    return False


def extract_investigators(study: dict) -> list[dict]:
    """Extract investigator information from a study."""
    protocol = study.get("protocolSection", {})
    investigators = []
    
    # Check overallOfficials
    contacts_module = protocol.get("contactsLocationsModule", {})
    overall_officials = contacts_module.get("overallOfficials", [])
    
    for official in overall_officials:
        name = official.get("name", "")
        role = official.get("role", "")
        affiliation = official.get("affiliation", "")
        
        if name:
            investigators.append({
                "full_name": name,
                "name_normalized": normalize_name(name),
                "role": role,
                "affiliation": affiliation,
                "affiliation_normalized": normalize_name(affiliation),
            })
    
    # Check responsibleParty
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    responsible_party = sponsor_module.get("responsibleParty", {})
    
    if responsible_party.get("investigatorFullName"):
        name = responsible_party["investigatorFullName"]
        affiliation = responsible_party.get("investigatorAffiliation", "")
        
        # Avoid duplicates
        if not any(inv["full_name"] == name for inv in investigators):
            investigators.append({
                "full_name": name,
                "name_normalized": normalize_name(name),
                "role": "PRINCIPAL_INVESTIGATOR",
                "affiliation": affiliation,
                "affiliation_normalized": normalize_name(affiliation),
            })
    
    return investigators


def extract_sites(study: dict) -> list[dict]:
    """Extract site information from a study."""
    protocol = study.get("protocolSection", {})
    contacts_module = protocol.get("contactsLocationsModule", {})
    locations = contacts_module.get("locations", [])
    
    sites = []
    for loc in locations:
        facility = loc.get("facility", "")
        city = loc.get("city", "")
        state = loc.get("state", "")
        country = loc.get("country", "")
        zip_code = loc.get("zip", "")
        status = loc.get("status", "")
        
        if facility or city:
            sites.append({
                "facility_name": facility,
                "facility_name_normalized": normalize_name(facility),
                "city": city,
                "state": state,
                "country": country,
                "zip": zip_code,
                "recruitment_status": status,
            })
    
    return sites


def extract_trial_data(study: dict) -> dict:
    """Extract trial data from a study."""
    protocol = study.get("protocolSection", {})
    id_module = protocol.get("identificationModule", {})
    status_module = protocol.get("statusModule", {})
    design_module = protocol.get("designModule", {})
    conditions_module = protocol.get("conditionsModule", {})
    description_module = protocol.get("descriptionModule", {})
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    
    # Parse dates
    def parse_date(date_struct):
        if not date_struct:
            return None
        date_str = date_struct.get("date", "")
        if not date_str:
            return None
        try:
            if len(date_str) == 7:  # YYYY-MM
                return f"{date_str}-01"
            elif len(date_str) == 4:  # YYYY
                return f"{date_str}-01-01"
            return date_str
        except:
            return None
    
    # Get phases
    phases = design_module.get("phases", [])
    phase_str = ", ".join(phases) if phases else None
    
    # Get enrollment
    enrollment_info = design_module.get("enrollmentInfo", {})
    enrollment = enrollment_info.get("count")
    enrollment_type = enrollment_info.get("type")
    
    # Get sponsor
    lead_sponsor = sponsor_module.get("leadSponsor", {})
    
    return {
        "nct_id": id_module.get("nctId"),
        "brief_title": id_module.get("briefTitle"),
        "official_title": id_module.get("officialTitle"),
        "brief_summary": description_module.get("briefSummary"),
        "conditions": conditions_module.get("conditions", []),
        "phase": phase_str,
        "study_type": design_module.get("studyType"),
        "overall_status": status_module.get("overallStatus"),
        "start_date": parse_date(status_module.get("startDateStruct")),
        "completion_date": parse_date(status_module.get("completionDateStruct")),
        "primary_completion_date": parse_date(status_module.get("primaryCompletionDateStruct")),
        "enrollment": enrollment,
        "enrollment_type": enrollment_type,
        "lead_sponsor_name": lead_sponsor.get("name"),
        "lead_sponsor_class": lead_sponsor.get("class"),
        "last_update_posted": parse_date(status_module.get("lastUpdatePostDateStruct")),
    }


def upsert_trial(trial_data: dict, avoid_search: bool) -> Optional[int]:
    """Insert or update a trial, return trial ID."""
    try:
        # Check if trial exists
        response = supabase.table("trials").select("id").eq("nct_id", trial_data["nct_id"]).limit(1).execute()
        
        if response.data:
            # Update existing trial
            trial_id = response.data[0]["id"]
            supabase.table("trials").update({
                **trial_data,
                "avoid_search": avoid_search,
                "updated_at": datetime.now().isoformat(),
            }).eq("id", trial_id).execute()
            return trial_id
        else:
            # Insert new trial
            insert_data = {**trial_data, "avoid_search": avoid_search}
            response = supabase.table("trials").insert(insert_data).execute()
            if response.data:
                return response.data[0]["id"]
    except Exception as e:
        # Silently continue on errors
        pass
    
    return None


def upsert_investigator(inv_data: dict) -> Optional[int]:
    """Insert or update an investigator, return investigator ID."""
    try:
        response = supabase.table("investigators").select("id").eq("full_name", inv_data["full_name"]).eq("affiliation", inv_data.get("affiliation", "")).limit(1).execute()
        
        if response.data:
            return response.data[0]["id"]
        else:
            response = supabase.table("investigators").insert(inv_data).execute()
            if response.data:
                return response.data[0]["id"]
    except:
        try:
            response = supabase.table("investigators").select("id").eq("full_name", inv_data["full_name"]).limit(1).execute()
            if response.data:
                return response.data[0]["id"]
        except:
            pass
    
    return None


def upsert_site(site_data: dict) -> Optional[int]:
    """Insert or update a site, return site ID."""
    try:
        response = supabase.table("sites").select("id").eq("facility_name", site_data["facility_name"]).eq("city", site_data.get("city", "")).eq("country", site_data.get("country", "")).limit(1).execute()
        
        if response.data:
            return response.data[0]["id"]
        else:
            insert_data = {k: v for k, v in site_data.items() if k != "recruitment_status"}
            response = supabase.table("sites").insert(insert_data).execute()
            if response.data:
                return response.data[0]["id"]
    except:
        try:
            response = supabase.table("sites").select("id").eq("facility_name", site_data["facility_name"]).limit(1).execute()
            if response.data:
                return response.data[0]["id"]
        except:
            pass
    
    return None


def link_trial_investigator(trial_id: int, investigator_id: int, role: str):
    """Create trial-investigator link."""
    try:
        supabase.table("trial_investigators").upsert({
            "trial_id": trial_id,
            "investigator_id": investigator_id,
            "role": role,
        }, on_conflict="trial_id,investigator_id").execute()
    except:
        pass


def link_trial_site(trial_id: int, site_id: int, status: str):
    """Create trial-site link."""
    try:
        supabase.table("trial_sites").upsert({
            "trial_id": trial_id,
            "site_id": site_id,
            "recruitment_status": status,
        }, on_conflict="trial_id,site_id").execute()
    except:
        pass


def link_investigator_site(investigator_id: int, site_id: int, trial_id: int):
    """Create investigator-site link."""
    try:
        supabase.table("investigator_sites").upsert({
            "investigator_id": investigator_id,
            "site_id": site_id,
            "trial_id": trial_id,
            "link_type": "oversight",
        }, on_conflict="investigator_id,site_id,trial_id,link_type").execute()
    except:
        pass


def import_study(study: dict) -> dict:
    """Import a single study and all its relationships."""
    result = {
        "nct_id": None,
        "success": False,
        "has_pi": False,
        "is_new": False,
    }
    
    # Extract data
    trial_data = extract_trial_data(study)
    investigators = extract_investigators(study)
    sites = extract_sites(study)
    
    result["nct_id"] = trial_data["nct_id"]
    result["has_pi"] = len(investigators) > 0
    
    # avoid_search = True if NO investigators
    avoid_search = not result["has_pi"]
    
    # Import trial
    trial_id = upsert_trial(trial_data, avoid_search)
    if not trial_id:
        return result
    
    # Import investigators and link to trial
    investigator_ids = []
    for inv in investigators:
        inv_id = upsert_investigator(inv)
        if inv_id:
            investigator_ids.append(inv_id)
            link_trial_investigator(trial_id, inv_id, inv.get("role", ""))
    
    # Import sites and link to trial (limit to first 20 sites to avoid timeout)
    site_ids = []
    for site in sites[:20]:
        site_id = upsert_site(site)
        if site_id:
            site_ids.append(site_id)
            link_trial_site(trial_id, site_id, site.get("recruitment_status", ""))
    
    # Link investigators to sites (limit combinations)
    for inv_id in investigator_ids[:3]:
        for site_id in site_ids[:5]:
            link_investigator_site(inv_id, site_id, trial_id)
    
    result["success"] = True
    return result


def load_progress() -> tuple[set, int]:
    """Load progress from previous run."""
    progress_file = os.path.join(OUTPUT_DIR, "import_progress.json")
    
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            data = json.load(f)
        return set(data.get("processed_nct_ids", [])), data.get("last_index", 0)
    
    return set(), 0


def save_progress(processed_nct_ids: set, last_index: int, stats: dict):
    """Save progress for resume capability."""
    progress_file = os.path.join(OUTPUT_DIR, "import_progress.json")
    
    with open(progress_file, "w") as f:
        json.dump({
            "saved_at": datetime.now().isoformat(),
            "processed_nct_ids": list(processed_nct_ids),
            "last_index": last_index,
            **stats,
        }, f)


def main():
    print("=" * 60)
    print("Import ALL Trials to Supabase")
    print("=" * 60)
    print()
    print(f"Input file: {CTG_FILE}")
    print(f"File size: {os.path.getsize(CTG_FILE) / (1024**3):.2f} GB")
    print()
    
    # Load progress
    processed_nct_ids, start_index = load_progress()
    
    if start_index > 0:
        print(f"Resuming from index {start_index:,} ({len(processed_nct_ids):,} already processed)")
    
    # Counters
    total_processed = 0
    imported_count = 0
    with_pi_count = 0
    without_pi_count = 0
    skipped_count = 0
    error_count = 0
    
    start_time = datetime.now()
    
    print("Streaming through JSON file...")
    print()
    
    with open(CTG_FILE, "rb") as f:
        studies = ijson.items(f, "item")
        
        for study in studies:
            total_processed += 1
            
            # Skip if before start index
            if total_processed <= start_index:
                continue
            
            # Get NCT ID
            nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
            
            # Skip if already processed
            if nct_id in processed_nct_ids:
                skipped_count += 1
                continue
            
            # Import the study
            result = import_study(study)
            
            if result["success"]:
                imported_count += 1
                processed_nct_ids.add(nct_id)
                
                if result["has_pi"]:
                    with_pi_count += 1
                else:
                    without_pi_count += 1
                
                if imported_count % 100 == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    rate = imported_count / elapsed if elapsed > 0 else 0
                    print(f"  Imported {imported_count:,} | With PI: {with_pi_count:,} | "
                          f"Without PI: {without_pi_count:,} | Rate: {rate:.1f}/sec")
            else:
                error_count += 1
            
            # Save progress periodically
            if total_processed % SAVE_INTERVAL == 0:
                save_progress(processed_nct_ids, total_processed, {
                    "imported_count": imported_count,
                    "with_pi_count": with_pi_count,
                    "without_pi_count": without_pi_count,
                })
            
            # Small delay to avoid overwhelming Supabase
            time.sleep(0.01)
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print()
    print("=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    print(f"Total studies scanned: {total_processed:,}")
    print(f"Successfully imported: {imported_count:,}")
    print(f"  - With PI (avoid_search=false): {with_pi_count:,}")
    print(f"  - Without PI (avoid_search=true): {without_pi_count:,}")
    print(f"Skipped (already processed): {skipped_count:,}")
    print(f"Errors: {error_count:,}")
    print(f"Time elapsed: {elapsed/60:.1f} minutes")
    print()
    
    # Save final log
    log_file = os.path.join(OUTPUT_DIR, "import_log.json")
    with open(log_file, "w") as f:
        json.dump({
            "completed_at": datetime.now().isoformat(),
            "total_scanned": total_processed,
            "imported_count": imported_count,
            "with_pi_count": with_pi_count,
            "without_pi_count": without_pi_count,
            "skipped_count": skipped_count,
            "error_count": error_count,
            "elapsed_seconds": elapsed,
        }, f, indent=2)
    
    print(f"Saved import log to: {log_file}")


if __name__ == "__main__":
    main()
