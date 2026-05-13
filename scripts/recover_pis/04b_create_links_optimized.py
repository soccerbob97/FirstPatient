#!/usr/bin/env python3
"""
Optimized version: Create missing trial_investigators links.
Uses batch queries to find which records need linking, avoiding slow per-record checks.
"""

import os
import json
import psycopg2
from urllib.parse import quote_plus
from dotenv import load_dotenv

load_dotenv()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(SCRIPT_DIR, "recovered_pis_oncology_obesity.json")
BATCH_SIZE = 100


def get_db_connection():
    password = quote_plus(os.getenv("DATABASE_PASSWORD"))
    conn_string = f"postgresql://postgres:{password}@db.zwcreraudeemddmloeul.supabase.co:5432/postgres"
    return psycopg2.connect(conn_string)


def main():
    print("=" * 60)
    print("CREATE MISSING LINKS (OPTIMIZED)")
    print("=" * 60)
    
    # Load recovered PIs
    with open(INPUT_FILE) as f:
        data = json.load(f)
    pis = data.get("pis", [])
    print(f"Total recovered PIs: {len(pis):,}")
    
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Build lookup of NCT -> PI name
    nct_to_pi = {pi["nct_id"]: (pi.get("pi_name") or "")[:255] for pi in pis if pi.get("pi_name")}
    nct_ids = list(nct_to_pi.keys())
    print(f"NCT IDs with PI names: {len(nct_ids):,}")
    
    # Step 1: Find which NCT IDs already have links (batch query)
    print("\nChecking existing links...")
    cur.execute("""
        SELECT DISTINCT t.nct_id 
        FROM trial_investigators ti
        JOIN trials t ON ti.trial_id = t.id
        WHERE t.nct_id = ANY(%s)
    """, (nct_ids,))
    already_linked = set(row[0] for row in cur.fetchall())
    print(f"Already linked: {len(already_linked):,}")
    
    # Step 2: Filter to only NCT IDs that need linking
    need_linking = [nct for nct in nct_ids if nct not in already_linked]
    print(f"Need linking: {len(need_linking):,}")
    
    if not need_linking:
        print("\nAll records already linked!")
        return
    
    # Step 3: Get trial IDs for NCTs that need linking
    print("\nFetching trial IDs...")
    cur.execute("""
        SELECT nct_id, id FROM trials WHERE nct_id = ANY(%s)
    """, (need_linking,))
    nct_to_trial_id = {row[0]: row[1] for row in cur.fetchall()}
    print(f"Found trial IDs: {len(nct_to_trial_id):,}")
    
    # Step 4: Get investigator IDs for PI names
    pi_names = list(set(nct_to_pi[nct] for nct in need_linking if nct in nct_to_trial_id))
    print(f"\nFetching investigator IDs for {len(pi_names):,} unique names...")
    
    # Query in batches to avoid too large query
    name_to_inv_id = {}
    for i in range(0, len(pi_names), 1000):
        batch = pi_names[i:i+1000]
        cur.execute("""
            SELECT full_name, id FROM investigators WHERE full_name = ANY(%s)
        """, (batch,))
        for row in cur.fetchall():
            name_to_inv_id[row[0]] = row[1]
    print(f"Found investigator IDs: {len(name_to_inv_id):,}")
    
    # Step 5: Create links
    print("\nCreating links...")
    linked = 0
    skipped_no_trial = 0
    skipped_no_inv = 0
    errors = 0
    
    for nct_id in need_linking:
        pi_name = nct_to_pi[nct_id]
        trial_id = nct_to_trial_id.get(nct_id)
        inv_id = name_to_inv_id.get(pi_name)
        
        if not trial_id:
            skipped_no_trial += 1
            continue
        if not inv_id:
            skipped_no_inv += 1
            continue
        
        try:
            cur.execute("SAVEPOINT sp1")
            
            # Create link
            cur.execute("""
                INSERT INTO trial_investigators (trial_id, investigator_id, role)
                VALUES (%s, %s, %s)
            """, (trial_id, inv_id, "PRINCIPAL_INVESTIGATOR"))
            
            # Update avoid_search
            cur.execute("""
                UPDATE trials SET avoid_search = false WHERE id = %s
            """, (trial_id,))
            
            cur.execute("RELEASE SAVEPOINT sp1")
            linked += 1
            
            if linked % BATCH_SIZE == 0:
                conn.commit()
                print(f"  Linked {linked:,}...")
                
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error for {nct_id}: {e}")
            cur.execute("ROLLBACK TO SAVEPOINT sp1")
    
    conn.commit()
    cur.close()
    conn.close()
    
    print()
    print("=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print(f"Links created: {linked:,}")
    print(f"Skipped (no trial): {skipped_no_trial:,}")
    print(f"Skipped (no investigator): {skipped_no_inv:,}")
    print(f"Errors: {errors:,}")


if __name__ == "__main__":
    main()
