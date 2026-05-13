#!/usr/bin/env python3
"""
Fast batch import of ALL trials using direct PostgreSQL connection.

This is much faster than the Supabase REST API approach.
Uses batch inserts and ON CONFLICT for upserts.

Usage:
    python scripts/import_trials/03_fast_import_trials.py
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
        "avoid_search": not has_investigator(study),
    }


def extract_investigators(study: dict) -> list[dict]:
    """Extract investigators from a study."""
    protocol = study.get("protocolSection", {})
    investigators = []
    
    contacts_module = protocol.get("contactsLocationsModule", {})
    for official in contacts_module.get("overallOfficials", []):
        name = official.get("name", "")
        if name:
            investigators.append({
                "full_name": name[:255],
                "name_normalized": normalize_name(name),
                "role": official.get("role"),
                "affiliation": (official.get("affiliation") or "")[:500],
                "affiliation_normalized": normalize_name(official.get("affiliation") or ""),
            })
    
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    responsible_party = sponsor_module.get("responsibleParty", {})
    if responsible_party.get("investigatorFullName"):
        name = responsible_party["investigatorFullName"]
        if not any(inv["full_name"] == name for inv in investigators):
            investigators.append({
                "full_name": name[:255],
                "name_normalized": normalize_name(name),
                "role": "PRINCIPAL_INVESTIGATOR",
                "affiliation": (responsible_party.get("investigatorAffiliation") or "")[:500],
                "affiliation_normalized": normalize_name(responsible_party.get("investigatorAffiliation") or ""),
            })
    
    return investigators


def batch_upsert_trials(cur, trials: list[dict]):
    """Batch upsert trials."""
    if not trials:
        return
    
    sql = """
        INSERT INTO trials (nct_id, brief_title, official_title, brief_summary, conditions, 
                           phase, study_type, overall_status, start_date, completion_date,
                           primary_completion_date, enrollment, enrollment_type, 
                           lead_sponsor_name, lead_sponsor_class, last_update_posted, avoid_search)
        VALUES %s
        ON CONFLICT (nct_id) DO UPDATE SET
            brief_title = EXCLUDED.brief_title,
            official_title = EXCLUDED.official_title,
            brief_summary = EXCLUDED.brief_summary,
            conditions = EXCLUDED.conditions,
            phase = EXCLUDED.phase,
            study_type = EXCLUDED.study_type,
            overall_status = EXCLUDED.overall_status,
            start_date = EXCLUDED.start_date,
            completion_date = EXCLUDED.completion_date,
            primary_completion_date = EXCLUDED.primary_completion_date,
            enrollment = EXCLUDED.enrollment,
            enrollment_type = EXCLUDED.enrollment_type,
            lead_sponsor_name = EXCLUDED.lead_sponsor_name,
            lead_sponsor_class = EXCLUDED.lead_sponsor_class,
            last_update_posted = EXCLUDED.last_update_posted,
            avoid_search = EXCLUDED.avoid_search,
            updated_at = NOW()
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


def batch_upsert_investigators(cur, investigators: list[dict]) -> dict:
    """Batch upsert investigators and return name->id mapping."""
    if not investigators:
        return {}
    
    # Deduplicate by full_name + affiliation
    unique_invs = {}
    for inv in investigators:
        key = (inv["full_name"], inv.get("affiliation", ""))
        if key not in unique_invs:
            unique_invs[key] = inv
    
    sql = """
        INSERT INTO investigators (full_name, name_normalized, role, affiliation, affiliation_normalized)
        VALUES %s
        ON CONFLICT (full_name, affiliation) DO UPDATE SET
            name_normalized = EXCLUDED.name_normalized,
            role = COALESCE(EXCLUDED.role, investigators.role),
            affiliation_normalized = EXCLUDED.affiliation_normalized
        RETURNING id, full_name, affiliation
    """
    
    values = [
        (inv["full_name"], inv["name_normalized"], inv.get("role"), 
         inv.get("affiliation", ""), inv["affiliation_normalized"])
        for inv in unique_invs.values()
    ]
    
    try:
        execute_values(cur, sql, values, fetch=True)
        results = cur.fetchall()
        return {(r[1], r[2]): r[0] for r in results}
    except:
        return {}


def load_progress() -> int:
    """Load last processed index."""
    progress_file = os.path.join(OUTPUT_DIR, "fast_import_progress.json")
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            return json.load(f).get("last_index", 0)
    return 0


def save_progress(last_index: int, stats: dict):
    """Save progress."""
    progress_file = os.path.join(OUTPUT_DIR, "fast_import_progress.json")
    with open(progress_file, "w") as f:
        json.dump({"last_index": last_index, "saved_at": datetime.now().isoformat(), **stats}, f)


def main():
    print("=" * 60)
    print("Fast Import ALL Trials (Direct PostgreSQL)")
    print("=" * 60)
    print()
    
    # Connect to database
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()
    
    # Load progress
    start_index = load_progress()
    if start_index > 0:
        print(f"Resuming from index {start_index:,}")
    
    # Counters
    total_processed = 0
    imported_count = 0
    with_pi_count = 0
    without_pi_count = 0
    
    # Batch buffers
    trial_batch = []
    investigator_batch = []
    
    start_time = datetime.now()
    
    print(f"Streaming through {CTG_FILE}...")
    print()
    
    with open(CTG_FILE, "rb") as f:
        studies = ijson.items(f, "item")
        
        for study in studies:
            total_processed += 1
            
            # Skip if before start index
            if total_processed <= start_index:
                if total_processed % 50000 == 0:
                    print(f"  Skipping to {total_processed:,}...")
                continue
            
            # Extract data
            trial = extract_trial(study)
            investigators = extract_investigators(study)
            
            if trial["avoid_search"]:
                without_pi_count += 1
            else:
                with_pi_count += 1
            
            trial_batch.append(trial)
            investigator_batch.extend(investigators)
            
            # Process batch
            if len(trial_batch) >= BATCH_SIZE:
                try:
                    batch_upsert_trials(cur, trial_batch)
                    batch_upsert_investigators(cur, investigator_batch)
                    conn.commit()
                    imported_count += len(trial_batch)
                except Exception as e:
                    print(f"  Error at {total_processed}: {e}")
                    conn.rollback()
                
                trial_batch = []
                investigator_batch = []
                
                if imported_count % 1000 == 0:
                    elapsed = (datetime.now() - start_time).total_seconds()
                    rate = imported_count / elapsed if elapsed > 0 else 0
                    remaining = (579013 - total_processed) / rate / 3600 if rate > 0 else 0
                    print(f"  Imported {imported_count:,} | With PI: {with_pi_count:,} | "
                          f"Without PI: {without_pi_count:,} | Rate: {rate:.1f}/sec | ETA: {remaining:.1f}h")
                    
                    save_progress(total_processed, {
                        "imported_count": imported_count,
                        "with_pi_count": with_pi_count,
                        "without_pi_count": without_pi_count,
                    })
    
    # Process remaining batch
    if trial_batch:
        try:
            batch_upsert_trials(cur, trial_batch)
            batch_upsert_investigators(cur, investigator_batch)
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
    print(f"Total processed: {total_processed:,}")
    print(f"Imported: {imported_count:,}")
    print(f"  - With PI: {with_pi_count:,}")
    print(f"  - Without PI: {without_pi_count:,}")
    print(f"Time: {elapsed/60:.1f} minutes ({elapsed/3600:.2f} hours)")
    print(f"Rate: {imported_count/elapsed:.1f} trials/sec")
    
    # Save final log
    log_file = os.path.join(OUTPUT_DIR, "fast_import_log.json")
    with open(log_file, "w") as f:
        json.dump({
            "completed_at": datetime.now().isoformat(),
            "total_processed": total_processed,
            "imported_count": imported_count,
            "with_pi_count": with_pi_count,
            "without_pi_count": without_pi_count,
            "elapsed_seconds": elapsed,
            "rate_per_sec": imported_count / elapsed if elapsed > 0 else 0,
        }, f, indent=2)


if __name__ == "__main__":
    main()
