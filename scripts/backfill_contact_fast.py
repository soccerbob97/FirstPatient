#!/usr/bin/env python3
"""
FAST backfill contact info for obesity/oncology investigators.

Optimizations:
1. Pre-load all investigator name->id mappings into memory
2. Filter JSON for obesity/oncology trials only
3. Batch updates (1000 at a time)
4. Use multiprocessing for JSON parsing
"""

import os
import sys
import json
import psycopg2
from psycopg2.extras import execute_batch
from urllib.parse import quote_plus
from dotenv import load_dotenv
from concurrent.futures import ProcessPoolExecutor, as_completed
import multiprocessing as mp

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv()

from src.ingestion.parser import normalize_name

JSON_FILE = "/Users/harshakaranth/Harsha/Projects/ClinicalTrialProject/ctg-studies_full.json"

# Keywords to filter for obesity/oncology
KEYWORDS = [
    'obesity', 'obese', 'overweight', 'weight loss', 'bariatric',
    'oncology', 'cancer', 'tumor', 'tumour', 'carcinoma', 'lymphoma', 
    'leukemia', 'melanoma', 'sarcoma', 'myeloma', 'neoplasm'
]


def get_db_connection():
    password = quote_plus(os.getenv("DATABASE_PASSWORD"))
    conn_string = f"postgresql://postgres:{password}@db.zwcreraudeemddmloeul.supabase.co:5432/postgres"
    return psycopg2.connect(conn_string)


def is_obesity_oncology_trial(study: dict) -> bool:
    """Check if trial is obesity or oncology related."""
    protocol = study.get("protocolSection", {})
    
    # Check conditions
    conditions_module = protocol.get("conditionsModule", {})
    conditions = conditions_module.get("conditions", [])
    keywords_text = " ".join(conditions).lower()
    
    # Check title and description
    id_module = protocol.get("identificationModule", {})
    title = (id_module.get("briefTitle", "") + " " + id_module.get("officialTitle", "")).lower()
    
    desc_module = protocol.get("descriptionModule", {})
    description = desc_module.get("briefSummary", "").lower()
    
    combined = keywords_text + " " + title + " " + description
    
    return any(kw in combined for kw in KEYWORDS)


def extract_contacts(study: dict) -> list[dict]:
    """Extract contacts from a study."""
    contacts = []
    protocol = study.get("protocolSection", {})
    contacts_module = protocol.get("contactsLocationsModule", {})
    
    for loc in contacts_module.get("locations", []):
        for contact in loc.get("contacts", []):
            name = contact.get("name")
            email = contact.get("email")
            phone = contact.get("phone")
            
            if name and (email or phone):
                contacts.append({
                    "name": name,
                    "name_normalized": normalize_name(name),
                    "email": email,
                    "phone": phone,
                })
    return contacts


def load_investigator_mappings(conn) -> dict:
    """Load all investigator name_normalized -> (id, email, phone) mappings."""
    print("Loading investigator mappings into memory...")
    cur = conn.cursor()
    cur.execute("SELECT id, name_normalized, email, phone FROM investigators WHERE name_normalized IS NOT NULL")
    
    mappings = {}
    for row in cur.fetchall():
        inv_id, name_norm, email, phone = row
        if name_norm:
            mappings[name_norm] = {"id": inv_id, "email": email, "phone": phone}
    
    print(f"  Loaded {len(mappings):,} investigator mappings")
    return mappings


def process_json_chunk(start_byte: int, end_byte: int, chunk_id: int) -> list[dict]:
    """Process a chunk of the JSON file. Returns list of contacts found."""
    # This is a simplified approach - we'll use streaming instead
    pass


def main():
    print("=" * 60)
    print("FAST Backfill: Obesity/Oncology Contact Info")
    print("=" * 60)
    
    if not os.path.exists(JSON_FILE):
        print(f"ERROR: JSON file not found: {JSON_FILE}")
        return
    
    file_size = os.path.getsize(JSON_FILE) / (1024**3)
    print(f"JSON file: {file_size:.2f} GB")
    
    conn = get_db_connection()
    
    # Load all investigator mappings into memory (fast lookup)
    inv_mappings = load_investigator_mappings(conn)
    
    # Stream through JSON, filter for obesity/oncology, collect updates
    print("\nStreaming JSON and filtering for obesity/oncology trials...")
    
    import ijson
    
    updates_to_apply = []  # List of (inv_id, email, phone)
    total_processed = 0
    obesity_oncology_count = 0
    contacts_found = 0
    
    with open(JSON_FILE, "rb") as f:
        studies = ijson.items(f, "item")
        
        for study in studies:
            total_processed += 1
            
            # Filter for obesity/oncology
            if not is_obesity_oncology_trial(study):
                if total_processed % 100000 == 0:
                    print(f"  Scanned {total_processed:,} trials, found {obesity_oncology_count:,} obesity/oncology...")
                continue
            
            obesity_oncology_count += 1
            
            # Extract contacts
            contacts = extract_contacts(study)
            contacts_found += len(contacts)
            
            for contact in contacts:
                name_norm = contact.get("name_normalized")
                if not name_norm or name_norm not in inv_mappings:
                    continue
                
                inv = inv_mappings[name_norm]
                
                # Only add if we have new info
                new_email = contact.get("email") if not inv["email"] else None
                new_phone = contact.get("phone") if not inv["phone"] else None
                
                if new_email or new_phone:
                    updates_to_apply.append({
                        "id": inv["id"],
                        "email": new_email,
                        "phone": new_phone
                    })
                    # Update local cache to avoid duplicates
                    if new_email:
                        inv_mappings[name_norm]["email"] = new_email
                    if new_phone:
                        inv_mappings[name_norm]["phone"] = new_phone
            
            if obesity_oncology_count % 10000 == 0:
                print(f"  Processed {obesity_oncology_count:,} obesity/oncology trials, {len(updates_to_apply):,} updates pending...")
    
    print(f"\nScan complete!")
    print(f"  Total trials scanned: {total_processed:,}")
    print(f"  Obesity/oncology trials: {obesity_oncology_count:,}")
    print(f"  Contacts found: {contacts_found:,}")
    print(f"  Updates to apply: {len(updates_to_apply):,}")
    
    # Apply updates in batches using execute_batch for speed
    if updates_to_apply:
        print(f"\nApplying {len(updates_to_apply):,} updates using batch execution...")
        cur = conn.cursor()
        
        # Separate into email-only, phone-only, and both updates
        email_only = [(u["email"], u["id"]) for u in updates_to_apply if u["email"] and not u["phone"]]
        phone_only = [(u["phone"], u["id"]) for u in updates_to_apply if u["phone"] and not u["email"]]
        both = [(u["email"], u["phone"], u["id"]) for u in updates_to_apply if u["email"] and u["phone"]]
        
        print(f"  Email-only: {len(email_only):,}, Phone-only: {len(phone_only):,}, Both: {len(both):,}")
        
        # Batch execute email updates
        if email_only:
            execute_batch(cur, "UPDATE investigators SET email = %s WHERE id = %s", email_only, page_size=500)
            conn.commit()
            print(f"  ✓ Applied {len(email_only):,} email updates")
        
        # Batch execute phone updates
        if phone_only:
            execute_batch(cur, "UPDATE investigators SET phone = %s WHERE id = %s", phone_only, page_size=500)
            conn.commit()
            print(f"  ✓ Applied {len(phone_only):,} phone updates")
        
        # Batch execute both updates
        if both:
            execute_batch(cur, "UPDATE investigators SET email = %s, phone = %s WHERE id = %s", both, page_size=500)
            conn.commit()
            print(f"  ✓ Applied {len(both):,} email+phone updates")
        
        print(f"\nTotal updates applied: {len(updates_to_apply):,}")
    
    conn.close()
    print("\n" + "=" * 60)
    print("DONE!")
    print("=" * 60)


if __name__ == "__main__":
    main()
