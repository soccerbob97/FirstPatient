#!/usr/bin/env python3
"""
Import ONLY missing oncology/diabetes trials from ctg-studies_full.json.

This script:
1. Fetches existing NCT IDs from database
2. Streams through JSON, filtering for oncology/diabetes trials
3. Imports ONLY trials that don't exist in DB
4. Sets avoid_search=true for all (since they don't have PIs)

Usage:
    python scripts/import_trials/04_import_missing_oncology_diabetes.py
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

# Keywords for filtering
ONCOLOGY_KEYWORDS = [
    "cancer", "tumor", "tumour", "carcinoma", "lymphoma", "leukemia", "leukaemia",
    "melanoma", "sarcoma", "myeloma", "oncology", "neoplasm", "malignant",
    "metastatic", "chemotherapy", "immunotherapy", "pd-1", "pd-l1", "car-t",
    "breast cancer", "lung cancer", "prostate cancer", "colorectal cancer",
    "pancreatic cancer", "ovarian cancer", "bladder cancer", "kidney cancer",
    "liver cancer", "brain cancer", "glioblastoma", "neuroblastoma"
]

DIABETES_KEYWORDS = [
    "diabetes", "diabetic", "type 1 diabetes", "type 2 diabetes", "t1d", "t2d",
    "insulin", "glucose", "glycemic", "hba1c", "hyperglycemia", "hypoglycemia",
    "metformin", "glp-1", "sglt2", "dpp-4", "sulfonylurea",
    "semaglutide", "tirzepatide", "liraglutide", "dulaglutide",
    "ozempic", "mounjaro", "trulicity", "victoza"
]


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


def is_oncology_or_diabetes(study: dict) -> tuple[bool, str]:
    """Check if a study is related to oncology or diabetes."""
    protocol = study.get("protocolSection", {})
    
    conditions = protocol.get("conditionsModule", {}).get("conditions", [])
    title = protocol.get("identificationModule", {}).get("briefTitle", "")
    summary = protocol.get("descriptionModule", {}).get("briefSummary", "")
    keywords = protocol.get("conditionsModule", {}).get("keywords", [])
    
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
    
    # Check for diabetes
    for keyword in DIABETES_KEYWORDS:
        if keyword in search_text:
            return True, "diabetes"
    
    return False, None


def extract_trial(study: dict, category: str) -> dict:
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
        "avoid_search": True,  # All imported trials have avoid_search=true (no PI)
        "category": category,  # For logging only
    }


def get_existing_nct_ids(cur) -> set:
    """Fetch all existing NCT IDs from database."""
    print("Fetching existing NCT IDs from database...")
    cur.execute("SELECT nct_id FROM trials")
    existing = {row[0] for row in cur.fetchall()}
    print(f"Found {len(existing):,} existing trials in database")
    return existing


def batch_insert_trials(cur, trials: list[dict]):
    """Batch insert new trials (no upsert needed since we only insert missing)."""
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
    print("Import Missing Oncology/Diabetes Trials")
    print("=" * 60)
    print()
    
    # Connect to database
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    # Get existing NCT IDs
    existing_nct_ids = get_existing_nct_ids(cur)
    
    # Counters
    total_scanned = 0
    oncology_found = 0
    diabetes_found = 0
    already_exists = 0
    imported_count = 0
    
    # Batch buffer
    trial_batch = []
    
    start_time = datetime.now()
    
    print()
    print(f"Streaming through {CTG_FILE}...")
    print("Filtering for oncology/diabetes trials not in database...")
    print()
    
    with open(CTG_FILE, "rb") as f:
        studies = ijson.items(f, "item")
        
        for study in studies:
            total_scanned += 1
            
            # Check if oncology or diabetes
            is_match, category = is_oncology_or_diabetes(study)
            
            if not is_match:
                continue
            
            if category == "oncology":
                oncology_found += 1
            else:
                diabetes_found += 1
            
            # Get NCT ID
            nct_id = study.get("protocolSection", {}).get("identificationModule", {}).get("nctId")
            
            # Skip if already in database
            if nct_id in existing_nct_ids:
                already_exists += 1
                continue
            
            # Extract and add to batch
            trial = extract_trial(study, category)
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
                
                if imported_count % 500 == 0 and imported_count > 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    print(f"  Scanned {total_scanned:,} | Oncology: {oncology_found:,} | "
                          f"Diabetes: {diabetes_found:,} | Already in DB: {already_exists:,} | "
                          f"Imported: {imported_count:,}")
            
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
    print(f"Oncology trials found: {oncology_found:,}")
    print(f"Diabetes trials found: {diabetes_found:,}")
    print(f"Already in database: {already_exists:,}")
    print(f"Newly imported: {imported_count:,}")
    print(f"Time: {elapsed/60:.1f} minutes")
    print()
    print("All imported trials have avoid_search=true (no PI data)")
    
    # Save log
    log_file = os.path.join(OUTPUT_DIR, "oncology_diabetes_import_log.json")
    with open(log_file, "w") as f:
        json.dump({
            "completed_at": datetime.now().isoformat(),
            "total_scanned": total_scanned,
            "oncology_found": oncology_found,
            "diabetes_found": diabetes_found,
            "already_exists": already_exists,
            "imported_count": imported_count,
            "elapsed_seconds": elapsed,
        }, f, indent=2)
    
    print(f"Saved log to: {log_file}")


if __name__ == "__main__":
    main()
