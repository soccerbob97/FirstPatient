#!/usr/bin/env python3
"""
Backfill contact info (email, phone) for investigators from trials.raw_json.

This script extracts contact information from the stored raw JSON in trials
and updates the investigators table with email/phone where available.

Contact info is found in:
- protocolSection.contactsLocationsModule.locations[].contacts[]
"""

import os
import sys
import psycopg2
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

from src.ingestion.parser import normalize_name


def get_db_connection():
    password = quote_plus(os.getenv("DATABASE_PASSWORD"))
    conn_string = f"postgresql://postgres:{password}@db.zwcreraudeemddmloeul.supabase.co:5432/postgres"
    return psycopg2.connect(conn_string)


def extract_contacts_from_raw_json(raw_json: dict) -> list[dict]:
    """Extract contact info from raw JSON."""
    contacts = []
    
    protocol = raw_json.get("protocolSection", {})
    contacts_module = protocol.get("contactsLocationsModule", {})
    locations = contacts_module.get("locations", [])
    
    for loc in locations:
        facility = loc.get("facility")
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
                    "facility": facility,
                })
    
    return contacts


def main():
    import ijson
    
    # Path to the original bulk JSON file
    JSON_FILE = "/Users/harshakaranth/Harsha/Projects/ClinicalTrialProject/ctg-studies_full.json"
    
    print("=" * 60)
    print("Backfilling contact info for investigators")
    print("=" * 60)
    print()
    
    if not os.path.exists(JSON_FILE):
        print(f"ERROR: JSON file not found: {JSON_FILE}")
        print("Please ensure the ctg-studies_full.json file is available.")
        return
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # First, check if email/phone columns exist
    cur.execute("""
        SELECT column_name FROM information_schema.columns 
        WHERE table_name = 'investigators' AND column_name IN ('email', 'phone')
    """)
    existing_cols = [row[0] for row in cur.fetchall()]
    
    if 'email' not in existing_cols or 'phone' not in existing_cols:
        print("Adding email/phone columns to investigators table...")
        cur.execute("""
            ALTER TABLE investigators 
            ADD COLUMN IF NOT EXISTS email VARCHAR(255),
            ADD COLUMN IF NOT EXISTS phone VARCHAR(50)
        """)
        conn.commit()
        print("  Columns added!")
    else:
        print("Email/phone columns already exist.")
    
    print(f"\nStreaming from: {JSON_FILE}")
    print(f"File size: {os.path.getsize(JSON_FILE) / (1024**3):.2f} GB")
    print()
    
    total_updated = 0
    total_processed = 0
    total_contacts_found = 0
    batch_updates = 0
    
    with open(JSON_FILE, "rb") as f:
        studies = ijson.items(f, "item")
        
        for study in studies:
            total_processed += 1
            
            contacts = extract_contacts_from_raw_json(study)
            total_contacts_found += len(contacts)
            
            for contact in contacts:
                name_normalized = contact.get("name_normalized")
                if not name_normalized:
                    continue
                
                # Search by normalized name
                cur.execute("""
                    SELECT id, email, phone FROM investigators 
                    WHERE name_normalized = %s 
                    LIMIT 1
                """, (name_normalized,))
                inv_row = cur.fetchone()
                
                if not inv_row:
                    # Try partial match on full_name
                    cur.execute("""
                        SELECT id, email, phone FROM investigators 
                        WHERE full_name ILIKE %s 
                        LIMIT 1
                    """, (f"%{contact['name'][:30]}%",))
                    inv_row = cur.fetchone()
                
                if inv_row:
                    inv_id, existing_email, existing_phone = inv_row
                    
                    # Only update if we have new info
                    updates = []
                    params = []
                    if contact.get("email") and not existing_email:
                        updates.append("email = %s")
                        params.append(contact["email"])
                    if contact.get("phone") and not existing_phone:
                        updates.append("phone = %s")
                        params.append(contact["phone"])
                    
                    if updates:
                        params.append(inv_id)
                        cur.execute(f"""
                            UPDATE investigators 
                            SET {', '.join(updates)} 
                            WHERE id = %s
                        """, params)
                        total_updated += 1
                        batch_updates += 1
            
            # Commit every 1000 updates
            if batch_updates >= 100:
                conn.commit()
                batch_updates = 0
            
            if total_processed % 50000 == 0:
                conn.commit()
                print(f"  Processed {total_processed:,} trials | Contacts: {total_contacts_found:,} | Updated: {total_updated:,}")
    
    conn.commit()
    conn.close()
    
    print()
    print("=" * 60)
    print(f"Backfill complete!")
    print(f"  Total trials processed: {total_processed:,}")
    print(f"  Contacts found in JSON: {total_contacts_found:,}")
    print(f"  Investigators updated: {total_updated:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
