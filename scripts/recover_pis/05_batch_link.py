#!/usr/bin/env python3
"""
Fast batch linking - uses single SQL statements instead of per-record queries.
"""
import os
import json
import psycopg2
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(SCRIPT_DIR, "recovered_pis_oncology_obesity.json")

def get_db_connection():
    password = quote_plus(os.getenv("DATABASE_PASSWORD"))
    return psycopg2.connect(f"postgresql://postgres:{password}@db.zwcreraudeemddmloeul.supabase.co:5432/postgres")

def main():
    print("Loading JSON...")
    with open(INPUT_FILE) as f:
        pis = json.load(f)['pis']
    print(f"Total PIs: {len(pis)}")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Single SQL to insert all missing links at once
    print("Creating missing links (single batch SQL)...")
    cur.execute("""
        WITH recovered AS (
            SELECT unnest(%s::text[]) as nct_id, unnest(%s::text[]) as pi_name
        ),
        to_link AS (
            SELECT t.id as trial_id, i.id as investigator_id
            FROM recovered r
            JOIN trials t ON t.nct_id = r.nct_id
            JOIN investigators i ON i.full_name = r.pi_name
            WHERE NOT EXISTS (
                SELECT 1 FROM trial_investigators ti 
                WHERE ti.trial_id = t.id AND ti.investigator_id = i.id
            )
        )
        INSERT INTO trial_investigators (trial_id, investigator_id, role)
        SELECT trial_id, investigator_id, 'PRINCIPAL_INVESTIGATOR'
        FROM to_link
        ON CONFLICT DO NOTHING
    """, (
        [pi['nct_id'] for pi in pis],
        [(pi.get('pi_name') or '')[:255] for pi in pis]
    ))
    
    inserted = cur.rowcount
    print(f"Links inserted: {inserted}")
    
    # Update avoid_search for linked trials
    print("Updating avoid_search flags...")
    cur.execute("""
        UPDATE trials SET avoid_search = false
        WHERE nct_id = ANY(%s)
        AND EXISTS (
            SELECT 1 FROM trial_investigators ti WHERE ti.trial_id = trials.id
        )
    """, ([pi['nct_id'] for pi in pis],))
    
    updated = cur.rowcount
    print(f"Trials updated: {updated}")
    
    conn.commit()
    cur.close()
    conn.close()
    
    print("Done!")

if __name__ == "__main__":
    main()
