#!/usr/bin/env python3
"""
Import ALL remaining trials from ctg-studies_full.json.

This script:
1. Fetches existing NCT IDs from database
2. Imports ONLY trials that don't exist in DB
3. Sets avoid_search=true for trials without PI, false for trials with PI

Usage:
    python scripts/import_trials/05_import_all_remaining.py
"""

import os
import json
import ijson
import re
import time
from datetime import datetime
from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import execute_values

load_dotenv()

# Build database URL
supabase_url = os.getenv("SUPABASE_URL", "")
project_ref = supabase_url.split("//")[1].split(".")[0] if "supabase.co" in supabase_url else ""
db_password = os.getenv("DATABASE_PASSWORD", "")
encoded_password = quote_plus(db_password)
DATABASE_URL = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

# Input file
CTG_FILE = "/Users/harshakaranth/Harsha/Projects/ClinicalTrialProject/ctg-studies_full.json"

# Output directory
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Batch size
BATCH_SIZE = 100


def normalize_name(name: str) -> str:
    """Normalize a name for matching."""
    if not name:
        return ""
    return re.sub(r'[^a-z0-9\s]', '', name.lower()).strip()[:255]


def parse_date(date_struct):
    """Parse date from ClinicalTrials.gov format."""
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


def has_investigator(study: dict) -> bool:
    """Check if a study has investigator information."""
    protocol = study.get("protocolSection", {})
    
    contacts_module = protocol.get("contactsLocationsModule", {})
    overall_officials = contacts_module.get("overallOfficials", [])
    
    for official in overall_officials:
        if official.get("name"):
            return True
    
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    responsible_party = sponsor_module.get("responsibleParty", {})
    
    if responsible_party.get("investigatorFullName"):
        return True
    
    return False


def extract_trial(study: dict) -> dict:
    """Extract trial data from a study."""
    protocol = study.get("protocolSection", {})
    id_module = protocol.get("identificationModule", {})
    status_module = protocol.get("statusModule", {})
    design_module = protocol.get("designModule", {})
    conditions_module = protocol.get("conditionsModule", {})
    description_module = protocol.get("descriptionModule", {})
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    
    phases = design_module.get("phases", [])
    enrollment_info = design_module.get("enrollmentInfo", {})
    lead_sponsor = sponsor_module.get("leadSponsor", {})
    
    has_pi = has_investigator(study)
    
    return {
        "nct_id": id_module.get("nctId"),
        "brief_title": (id_module.get("briefTitle") or "")[:500],
        "official_title": (id_module.get("officialTitle") or "")[:1000],
        "brief_summary": description_module.get("briefSummary"),
        "conditions": conditions_module.get("conditions", []),
        "phase": ", ".join(phases) if phases else None,
        "study_type": design_module.get("studyType"),
        "overall_status": status_module.get("overallStatus"),
        "start_date": parse_date(status_module.get("startDateStruct")),
        "completion_date": parse_date(status_module.get("completionDateStruct")),
        "primary_completion_date": parse_date(status_module.get("primaryCompletionDateStruct")),
        "enrollment": enrollment_info.get("count"),
        "enrollment_type": enrollment_info.get("type"),
        "lead_sponsor_name": (lead_sponsor.get("name") or "")[:500],
        "lead_sponsor_class": lead_sponsor.get("class"),
        "last_update_posted": parse_date(status_module.get("lastUpdatePostDateStruct")),
        "avoid_search": not has_pi,  # True if no PI, False if has PI
        "has_pi": has_pi,  # For logging
    }


def get_existing_nct_ids(cur) -> set:
    """Fetch all existing NCT IDs from database."""
    print("Fetching existing NCT IDs from database...")
    cur.execute("SELECT nct_id FROM trials")
    existing = {row[0] for row in cur.fetchall()}
    print(f"Found {len(existing):,} existing trials in database")
    return existing


def batch_insert_trials(cur, trials: list[dict]):
    """Batch insert new trials."""
    if not trials:
        return 0
    
    sql = """
        INSERT INTO trials (nct_id, brief_title, official_title, brief_summary, conditions, 
                           phase, study_type, overall_status, start_date, completion_date,
                           primary_completion_date, enrollment, enrollment_type, 
                           lead_sponsor_name, lead_sponsor_class, last_update_posted, avoid_search)
        VALUES %s
        ON CONFLICT (nct_id) DO NOTHING
    """
    
    values = [
        (t["nct_id"], t["brief_title"], t["official_title"], t["brief_summary"],
         t["conditions"], t["phase"], t["study_type"], t["overall_status"],
         t["start_date"], t["completion_date"], t["primary_completion_date"],
         t["enrollment"], t["enrollment_type"], t["lead_sponsor_name"],
         t["lead_sponsor_class"], t["last_update_posted"], t["avoid_search"])
        for t in trials
    ]
    
    execute_values(cur, sql, values)
    return len(trials)


def main():
    print("=" * 60)
    print("Import ALL Remaining Trials")
    print("=" * 60)
    print()
    
    # Connect to database
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    # Get existing NCT IDs
    existing_nct_ids = get_existing_nct_ids(cur)
    
    # Calculate expected remaining
    total_in_json = 579013
    expected_remaining = total_in_json - len(existing_nct_ids)
    print(f"Expected remaining trials to import: ~{expected_remaining:,}")
    print()
    
    # Counters
    total_scanned = 0
    already_exists = 0
    imported_count = 0
    with_pi_count = 0
    without_pi_count = 0
    
    # Batch buffer
    trial_batch = []
    
    start_time = datetime.now()
    
    print(f"Streaming through {CTG_FILE}...")
    print()
    
    with open(CTG_FILE, "rb") as f:
        studies = ijson.items(f, "item")
        
        for study in studies:
            total_scanned += 1
            
            # Get NCT ID
            nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
            
            # Skip if already in database
            if nct_id in existing_nct_ids:
                already_exists += 1
                continue
            
            # Extract trial data
            trial = extract_trial(study)
            
            if trial["has_pi"]:
                with_pi_count += 1
            else:
                without_pi_count += 1
            
            # Remove has_pi (not a DB column)
            del trial["has_pi"]
            
            trial_batch.append(trial)
            
            # Process batch
            if len(trial_batch) >= BATCH_SIZE:
                try:
                    batch_insert_trials(cur, trial_batch)
                    conn.commit()
                    imported_count += len(trial_batch)
                except Exception as e:
                    print(f"  Error: {e}")
                    conn.rollback()
                
                trial_batch = []
                
                if imported_count % 1000 == 0 and imported_count > 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    rate = imported_count / elapsed if elapsed > 0 else 0
                    remaining = (expected_remaining - imported_count) / rate / 60 if rate > 0 else 0
                    print(f"  Imported {imported_count:,} | With PI: {with_pi_count:,} | "
                          f"Without PI: {without_pi_count:,} | Rate: {rate:.0f}/sec | ETA: {remaining:.1f}min")
            
            # Progress update
            if total_scanned % 100000 == 0:
                print(f"  Scanned {total_scanned:,} studies...")
    
    # Process remaining batch
    if trial_batch:
        try:
            batch_insert_trials(cur, trial_batch)
            conn.commit()
            imported_count += len(trial_batch)
        except Exception as e:
            print(f"  Final batch error: {e}")
            conn.rollback()
    
    cur.close()
    conn.close()
    
    elapsed = (datetime.now() - start_time).total_seconds()
    
    print()
    print("=" * 60)
    print("IMPORT COMPLETE")
    print("=" * 60)
    print(f"Total studies scanned: {total_scanned:,}")
    print(f"Already in database: {already_exists:,}")
    print(f"Newly imported: {imported_count:,}")
    print(f"  - With PI (avoid_search=false): {with_pi_count:,}")
    print(f"  - Without PI (avoid_search=true): {without_pi_count:,}")
    print(f"Time: {elapsed/60:.1f} minutes")
    
    # Save log
    log_file = os.path.join(OUTPUT_DIR, "all_remaining_import_log.json")
    with open(log_file, "w") as f:
        json.dump({
            "completed_at": datetime.now().isoformat(),
            "total_scanned": total_scanned,
            "already_exists": already_exists,
            "imported_count": imported_count,
            "with_pi_count": with_pi_count,
            "without_pi_count": without_pi_count,
            "elapsed_seconds": elapsed,
        }, f, indent=2)
    
    print(f"Saved log to: {log_file}")


if __name__ == "__main__":
    main()
