#!/usr/bin/env python3
"""
Step 4: Create missing trial_investigators links for recovered PIs.

The investigators were created but the links weren't persisted due to a rollback bug.
This script:
1. Reads the recovered PIs JSON
2. Finds existing investigator by name
3. Creates trial_investigators link
4. Updates avoid_search=false on the trial

Run after: 03_import_recovered_pis.py (which created the investigators)
"""

import os
import json
import psycopg2
from urllib.parse import quote_plus
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


def create_links(pis: list, dry_run: bool = False):
    """Create missing trial_investigators links."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    linked = 0
    skipped_no_trial = 0
    skipped_no_investigator = 0
    skipped_already_linked = 0
    errors = 0
    
    for pi in pis:
        nct_id = pi["nct_id"]
        pi_name = (pi.get("pi_name") or "")[:255]
        
        if not pi_name:
            skipped_no_investigator += 1
            continue
        
        try:
            cur.execute("SAVEPOINT sp1")
            
            # 1. Get trial ID
            cur.execute("SELECT id FROM trials WHERE nct_id = %s", (nct_id,))
            result = cur.fetchone()
            if not result:
                cur.execute("ROLLBACK TO SAVEPOINT sp1")
                skipped_no_trial += 1
                continue
            trial_id = result[0]
            
            # 2. Find existing investigator by name
            cur.execute(
                "SELECT id FROM investigators WHERE full_name = %s",
                (pi_name,)
            )
            inv_result = cur.fetchone()
            if not inv_result:
                cur.execute("ROLLBACK TO SAVEPOINT sp1")
                skipped_no_investigator += 1
                continue
            investigator_id = inv_result[0]
            
            # 3. Check if link already exists
            cur.execute("""
                SELECT id FROM trial_investigators 
                WHERE trial_id = %s AND investigator_id = %s
            """, (trial_id, investigator_id))
            
            if cur.fetchone():
                cur.execute("ROLLBACK TO SAVEPOINT sp1")
                skipped_already_linked += 1
                continue
            
            if not dry_run:
                # 4. Create link
                cur.execute("""
                    INSERT INTO trial_investigators (trial_id, investigator_id, role)
                    VALUES (%s, %s, %s)
                """, (trial_id, investigator_id, "PRINCIPAL_INVESTIGATOR"))
                
                # 5. Update trial to be searchable
                cur.execute("""
                    UPDATE trials SET avoid_search = false WHERE id = %s
                """, (trial_id,))
            
            cur.execute("RELEASE SAVEPOINT sp1")
            linked += 1
            
            # Commit in batches
            if linked % BATCH_SIZE == 0:
                if not dry_run:
                    conn.commit()
                print(f"  {'[DRY RUN] ' if dry_run else ''}Linked {linked:,} PIs...")
                
        except Exception as e:
            errors += 1
            if errors <= 5:
                print(f"  Error for {nct_id}: {e}")
            cur.execute("ROLLBACK TO SAVEPOINT sp1")
    
    # Final commit
    if not dry_run:
        conn.commit()
    cur.close()
    conn.close()
    
    return linked, skipped_no_trial, skipped_no_investigator, skipped_already_linked, errors


def main():
    import sys
    
    dry_run = "--dry-run" in sys.argv
    
    print("=" * 60)
    print("CREATE MISSING TRIAL_INVESTIGATORS LINKS")
    print("=" * 60)
    if dry_run:
        print("*** DRY RUN MODE - No changes will be made ***")
    print()
    
    # Load recovered PIs
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found")
        return
    
    with open(INPUT_FILE) as f:
        data = json.load(f)
    
    pis = data.get("pis", [])
    print(f"Recovered PIs to link: {len(pis):,}")
    print()
    
    # Create links
    print("Creating links...")
    linked, no_trial, no_inv, already_linked, errors = create_links(pis, dry_run=dry_run)
    
    print()
    print("=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print(f"Links created: {linked:,}")
    print(f"Skipped (trial not found): {no_trial:,}")
    print(f"Skipped (investigator not found): {no_inv:,}")
    print(f"Skipped (already linked): {already_linked:,}")
    print(f"Errors: {errors:,}")
    
    if not dry_run:
        print()
        print("Verifying...")
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Check a sample
        cur.execute("""
            SELECT t.nct_id, i.full_name
            FROM trial_investigators ti
            JOIN trials t ON ti.trial_id = t.id
            JOIN investigators i ON ti.investigator_id = i.id
            WHERE ti.role = 'PRINCIPAL_INVESTIGATOR'
            ORDER BY ti.id DESC
            LIMIT 5
        """)
        print("Sample of recent links:")
        for row in cur.fetchall():
            print(f"  {row[0]}: {row[1]}")
        
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
