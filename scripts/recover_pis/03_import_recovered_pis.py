#!/usr/bin/env python3
"""
Step 3: Import recovered PIs into the database.

This script:
1. Creates new investigator records for recovered PIs
2. Links investigators to trials via trial_investigators
3. Updates avoid_search=false for trials with recovered PIs

Run after: 02_search_pubmed_targeted.py
"""

import os
import json
import psycopg2
from urllib.parse import quote_plus
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(SCRIPT_DIR, "recovered_pis_oncology_obesity.json")
BATCH_SIZE = 100


def get_db_connection():
    password = quote_plus(os.getenv("DATABASE_PASSWORD"))
    conn_string = f"postgresql://postgres:{password}@db.zwcreraudeemddmloeul.supabase.co:5432/postgres"
    return psycopg2.connect(conn_string)


def import_pis(pis: list):
    """Import recovered PIs into the database."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    imported = 0
    skipped = 0
    errors = 0
    
    for pi in pis:
        nct_id = pi["nct_id"]
        pi_name = (pi.get("pi_name") or "")[:255]
        pi_affiliation = (pi.get("pi_affiliation") or "")[:450]  # Leave room for safety
        
        if not pi_name:
            skipped += 1
            continue
        
        try:
            # Use savepoint so errors don't rollback the whole batch
            cur.execute("SAVEPOINT sp1")
            
            # 1. Get trial ID
            cur.execute("SELECT id FROM trials WHERE nct_id = %s", (nct_id,))
            result = cur.fetchone()
            if not result:
                cur.execute("ROLLBACK TO SAVEPOINT sp1")
                skipped += 1
                continue
            trial_id = result[0]
            
            # 2. Check if investigator already exists (by name)
            cur.execute(
                "SELECT id FROM investigators WHERE full_name = %s",
                (pi_name,)
            )
            inv_result = cur.fetchone()
            
            if inv_result:
                investigator_id = inv_result[0]
            else:
                # Create new investigator
                cur.execute("""
                    INSERT INTO investigators (full_name, affiliation)
                    VALUES (%s, %s)
                    RETURNING id
                """, (pi_name, pi_affiliation))
                investigator_id = cur.fetchone()[0]
            
            # 3. Check if link already exists
            cur.execute("""
                SELECT id FROM trial_investigators 
                WHERE trial_id = %s AND investigator_id = %s
            """, (trial_id, investigator_id))
            
            if not cur.fetchone():
                # Create link
                cur.execute("""
                    INSERT INTO trial_investigators (trial_id, investigator_id, role)
                    VALUES (%s, %s, %s)
                """, (trial_id, investigator_id, "PRINCIPAL_INVESTIGATOR"))
            
            # 4. Update trial to be searchable
            cur.execute("""
                UPDATE trials SET avoid_search = false WHERE id = %s
            """, (trial_id,))
            
            cur.execute("RELEASE SAVEPOINT sp1")
            imported += 1
            
            # Commit in batches
            if imported % BATCH_SIZE == 0:
                conn.commit()
                print(f"  Imported {imported:,} PIs...")
                
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error for {nct_id}: {e}")
            cur.execute("ROLLBACK TO SAVEPOINT sp1")
    
    # Final commit
    conn.commit()
    cur.close()
    conn.close()
    
    return imported, skipped, errors


def main():
    print("=" * 60)
    print("IMPORT RECOVERED PIs INTO DATABASE")
    print("=" * 60)
    print()
    
    # Load recovered PIs
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found")
        print("Run 02_search_pubmed_targeted.py first")
        return
    
    with open(INPUT_FILE) as f:
        data = json.load(f)
    
    pis = data.get("pis", [])
    print(f"Recovered PIs to import: {len(pis):,}")
    print()
    
    # Import
    print("Importing...")
    imported, skipped, errors = import_pis(pis)
    
    print()
    print("=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print(f"Imported: {imported:,}")
    print(f"Skipped (trial not found): {skipped:,}")
    print(f"Errors: {errors:,}")
    print()
    
    # Verify
    print("Verifying...")
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            COUNT(*) FILTER (WHERE avoid_search = false) as with_pi,
            COUNT(*) FILTER (WHERE avoid_search = true) as without_pi
        FROM trials
        WHERE conditions::text ILIKE '%cancer%'
           OR conditions::text ILIKE '%tumor%'
           OR conditions::text ILIKE '%carcinoma%'
           OR conditions::text ILIKE '%lymphoma%'
           OR conditions::text ILIKE '%leukemia%'
           OR conditions::text ILIKE '%melanoma%'
           OR conditions::text ILIKE '%obesity%'
           OR conditions::text ILIKE '%diabetes%'
    """)
    with_pi, without_pi = cur.fetchone()
    
    print(f"Oncology/Obesity trials with PI: {with_pi:,}")
    print(f"Oncology/Obesity trials without PI: {without_pi:,}")
    
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
