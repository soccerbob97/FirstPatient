#!/usr/bin/env python3
"""
Import ALL trials from ctg-studies_full.json to Supabase.

This script:
1. Streams through the 9GB JSON file
2. Imports ALL trials, investigators, sites, and relationships
3. Sets avoid_search=true for trials WITHOUT investigators

Usage:
    python scripts/import_trials/01_filter_and_import_trials.py
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
SAVE_INTERVAL = 1000


def normalize_name(name: str) -> str:
    """Normalize a name for matching."""
    if not name:
        return ""
    return re.sub(r'[^a-z0-9\s]', '', name.lower()).strip()


def is_oncology_or_obesity(study: dict) -> tuple[bool, str]:
    """
    Check if a study is related to oncology or obesity.
    
    Returns (is_match, category) where category is 'oncology', 'obesity', or None.
    """
    protocol = study.get("protocolSection", {})
    
    # Get searchable text
    conditions = protocol.get("conditionsModule", {}).get("conditions", [])
    title = protocol.get("identificationModule", {}).get("briefTitle", "")
    summary = protocol.get("descriptionModule", {}).get("briefSummary", "")
    keywords = protocol.get("conditionsModule", {}).get("keywords", [])
    
    # Combine all text
    search_text = " ".join([
        title,
        summary,
        " ".join(conditions),
        " ".join(keywords)
    ]).lower()
    
    # Check for oncology
    for keyword in ONCOLOGY_KEYWORDS:
        if keyword in search_text:
            return True, "oncology"
    
    # Check for obesity
    for keyword in OBESITY_KEYWORDS:
        if keyword in search_text:
            return True, "obesity"
    
    return False, None


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


def extract_trial_data(study: dict, category: str) -> dict:
    """Extract trial data from a study."""
    protocol = study.get("protocolSection", {})
    id_module = protocol.get("identificationModule", {})
    status_module = protocol.get("statusModule", {})
    design_module = protocol.get("designModule", {})
    conditions_module = protocol.get("conditionsModule", {})
    description_module = protocol.get("descriptionModule", {})
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    enrollment_module = protocol.get("eligibilityModule", {})
    
    # Parse dates
    def parse_date(date_struct):
        if not date_struct:
            return None
        date_str = date_struct.get("date", "")
        if not date_str:
            return None
        # Handle various date formats
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
        "category": category,  # oncology or obesity
    }


def upsert_trial(trial_data: dict, has_pi: bool) -> Optional[int]:
    """Insert or update a trial, return trial ID."""
    try:
        # Check if trial exists
        response = supabase.table("trials").select("id").eq("nct_id", trial_data["nct_id"]).limit(1).execute()
        
        if response.data:
            # Update existing trial
            trial_id = response.data[0]["id"]
            supabase.table("trials").update({
                **{k: v for k, v in trial_data.items() if k != "category"},
                "has_pi": has_pi,
                "updated_at": datetime.now().isoformat(),
            }).eq("id", trial_id).execute()
            return trial_id
        else:
            # Insert new trial
            insert_data = {k: v for k, v in trial_data.items() if k != "category"}
            insert_data["has_pi"] = has_pi
            response = supabase.table("trials").insert(insert_data).execute()
            if response.data:
                return response.data[0]["id"]
    except Exception as e:
        print(f"    Error upserting trial {trial_data.get('nct_id')}: {e}")
    
    return None


def upsert_investigator(inv_data: dict) -> Optional[int]:
    """Insert or update an investigator, return investigator ID."""
    try:
        # Check if investigator exists
        response = supabase.table("investigators").select("id").eq("full_name", inv_data["full_name"]).eq("affiliation", inv_data.get("affiliation", "")).limit(1).execute()
        
        if response.data:
            return response.data[0]["id"]
        else:
            response = supabase.table("investigators").insert(inv_data).execute()
            if response.data:
                return response.data[0]["id"]
    except Exception as e:
        # Might be duplicate, try to fetch
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
        # Check if site exists
        response = supabase.table("sites").select("id").eq("facility_name", site_data["facility_name"]).eq("city", site_data.get("city", "")).eq("country", site_data.get("country", "")).limit(1).execute()
        
        if response.data:
            return response.data[0]["id"]
        else:
            insert_data = {k: v for k, v in site_data.items() if k != "recruitment_status"}
            response = supabase.table("sites").insert(insert_data).execute()
            if response.data:
                return response.data[0]["id"]
    except Exception as e:
        # Might be duplicate, try to fetch
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


def import_study(study: dict, category: str) -> dict:
    """Import a single study and all its relationships."""
    result = {
        "nct_id": None,
        "success": False,
        "has_pi": False,
        "investigators": 0,
        "sites": 0,
    }
    
    # Extract data
    trial_data = extract_trial_data(study, category)
    investigators = extract_investigators(study)
    sites = extract_sites(study)
    
    result["nct_id"] = trial_data["nct_id"]
    result["has_pi"] = len(investigators) > 0
    result["investigators"] = len(investigators)
    result["sites"] = len(sites)
    
    # Import trial
    trial_id = upsert_trial(trial_data, result["has_pi"])
    if not trial_id:
        return result
    
    # Import investigators and link to trial
    investigator_ids = []
    for inv in investigators:
        inv_id = upsert_investigator(inv)
        if inv_id:
            investigator_ids.append(inv_id)
            link_trial_investigator(trial_id, inv_id, inv.get("role", ""))
    
    # Import sites and link to trial
    site_ids = []
    for site in sites:
        site_id = upsert_site(site)
        if site_id:
            site_ids.append(site_id)
            link_trial_site(trial_id, site_id, site.get("recruitment_status", ""))
    
    # Link investigators to sites (oversight relationship)
    for inv_id in investigator_ids:
        for site_id in site_ids:
            link_investigator_site(inv_id, site_id, trial_id)
    
    result["success"] = True
    return result


def main():
    print("=" * 60)
    print("Import Oncology & Obesity Trials to Supabase")
    print("=" * 60)
    print()
    print(f"Input file: {CTG_FILE}")
    print(f"File size: {os.path.getsize(CTG_FILE) / (1024**3):.2f} GB")
    print()
    
    # Counters
    total_processed = 0
    oncology_count = 0
    obesity_count = 0
    imported_count = 0
    with_pi_count = 0
    without_pi_count = 0
    error_count = 0
    
    start_time = datetime.now()
    
    print("Streaming through JSON file...")
    print()
    
    with open(CTG_FILE, "rb") as f:
        studies = ijson.items(f, "item")
        
        for study in studies:
            total_processed += 1
            
            # Check if oncology or obesity
            is_match, category = is_oncology_or_obesity(study)
            
            if is_match:
                if category == "oncology":
                    oncology_count += 1
                else:
                    obesity_count += 1
                
                # Import the study
                result = import_study(study, category)
                
                if result["success"]:
                    imported_count += 1
                    if result["has_pi"]:
                        with_pi_count += 1
                    else:
                        without_pi_count += 1
                    
                    if imported_count % 100 == 0:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        rate = imported_count / elapsed if elapsed > 0 else 0
                        print(f"  Imported {imported_count:,} trials | "
                              f"Oncology: {oncology_count:,} | Obesity: {obesity_count:,} | "
                              f"With PI: {with_pi_count:,} | Rate: {rate:.1f}/sec")
                else:
                    error_count += 1
                
                # Small delay to avoid overwhelming Supabase
                time.sleep(0.02)
            
            # Progress update
            if total_processed % 50000 == 0:
                print(f"  Scanned {total_processed:,} studies...")
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print()
    print("=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    print(f"Total studies scanned: {total_processed:,}")
    print(f"Oncology trials found: {oncology_count:,}")
    print(f"Obesity trials found: {obesity_count:,}")
    print(f"Successfully imported: {imported_count:,}")
    print(f"  - With PI: {with_pi_count:,}")
    print(f"  - Without PI: {without_pi_count:,}")
    print(f"Errors: {error_count:,}")
    print(f"Time elapsed: {elapsed/60:.1f} minutes")
    print()
    
    # Save import log
    log_file = os.path.join(OUTPUT_DIR, "import_log.json")
    with open(log_file, "w") as f:
        json.dump({
            "completed_at": datetime.now().isoformat(),
            "total_scanned": total_processed,
            "oncology_count": oncology_count,
            "obesity_count": obesity_count,
            "imported_count": imported_count,
            "with_pi_count": with_pi_count,
            "without_pi_count": without_pi_count,
            "error_count": error_count,
            "elapsed_seconds": elapsed,
        }, f, indent=2)
    
    print(f"Saved import log to: {log_file}")
    print()
    print("Next steps:")
    print("1. Run the migration to add has_pi column (if not done)")
    print("2. Generate embeddings for new trials")
    print("3. Update recommendation queries to filter by has_pi=true")


if __name__ == "__main__":
    main()
