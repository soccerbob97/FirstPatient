#!/usr/bin/env python3
"""
Step 1: Extract oncology and obesity/diabetes trials that are missing PIs.

Output: JSON file with ~27K trials to search for PIs.
"""

import os
import json
import psycopg2
from urllib.parse import quote_plus
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "oncology_obesity_without_pi.json")


def get_db_connection():
    password = quote_plus(os.getenv("DATABASE_PASSWORD"))
    conn_string = f"postgresql://postgres:{password}@db.zwcreraudeemddmloeul.supabase.co:5432/postgres"
    return psycopg2.connect(conn_string)


def extract_trials():
    """Extract oncology and obesity/diabetes trials without PIs."""
    conn = get_db_connection()
    cur = conn.cursor()
    
    print("Extracting oncology and obesity/diabetes trials without PIs...")
    
    # Query for oncology + obesity/diabetes trials with avoid_search=true
    cur.execute("""
        SELECT nct_id, brief_title, conditions, phase, overall_status, lead_sponsor_name
        FROM trials
        WHERE avoid_search = true
          AND (
            -- Oncology conditions
            conditions::text ILIKE '%cancer%'
            OR conditions::text ILIKE '%tumor%'
            OR conditions::text ILIKE '%tumour%'
            OR conditions::text ILIKE '%carcinoma%'
            OR conditions::text ILIKE '%lymphoma%'
            OR conditions::text ILIKE '%leukemia%'
            OR conditions::text ILIKE '%melanoma%'
            OR conditions::text ILIKE '%sarcoma%'
            OR conditions::text ILIKE '%neoplasm%'
            -- Obesity/Diabetes conditions
            OR conditions::text ILIKE '%obesity%'
            OR conditions::text ILIKE '%diabetes%'
            OR conditions::text ILIKE '%weight loss%'
            OR conditions::text ILIKE '%overweight%'
            OR brief_title ILIKE '%semaglutide%'
            OR brief_title ILIKE '%GLP-1%'
            OR brief_title ILIKE '%tirzepatide%'
            OR brief_title ILIKE '%ozempic%'
            OR brief_title ILIKE '%wegovy%'
          )
        ORDER BY 
            CASE 
                WHEN overall_status = 'COMPLETED' THEN 1
                WHEN overall_status = 'ACTIVE_NOT_RECRUITING' THEN 2
                WHEN overall_status = 'RECRUITING' THEN 3
                ELSE 4
            END,
            nct_id DESC
    """)
    
    rows = cur.fetchall()
    cur.close()
    conn.close()
    
    trials = []
    for row in rows:
        trials.append({
            "nct_id": row[0],
            "title": row[1],
            "conditions": row[2],
            "phase": row[3],
            "status": row[4],
            "sponsor": row[5],
        })
    
    return trials


def categorize_trials(trials):
    """Categorize trials into oncology vs obesity/diabetes."""
    oncology_keywords = ['cancer', 'tumor', 'tumour', 'carcinoma', 'lymphoma', 'leukemia', 'melanoma', 'sarcoma', 'neoplasm']
    obesity_keywords = ['obesity', 'diabetes', 'weight', 'overweight', 'semaglutide', 'glp-1', 'tirzepatide', 'ozempic', 'wegovy']
    
    oncology = []
    obesity_diabetes = []
    both = []
    
    for trial in trials:
        text = f"{trial.get('title', '')} {trial.get('conditions', '')}".lower()
        is_oncology = any(kw in text for kw in oncology_keywords)
        is_obesity = any(kw in text for kw in obesity_keywords)
        
        if is_oncology and is_obesity:
            both.append(trial)
        elif is_oncology:
            oncology.append(trial)
        elif is_obesity:
            obesity_diabetes.append(trial)
    
    return oncology, obesity_diabetes, both


def main():
    print("=" * 60)
    print("EXTRACT ONCOLOGY & OBESITY TRIALS WITHOUT PIs")
    print("=" * 60)
    print()
    
    trials = extract_trials()
    oncology, obesity_diabetes, both = categorize_trials(trials)
    
    print(f"Total trials without PIs (oncology + obesity): {len(trials):,}")
    print(f"  - Oncology only: {len(oncology):,}")
    print(f"  - Obesity/Diabetes only: {len(obesity_diabetes):,}")
    print(f"  - Both categories: {len(both):,}")
    print()
    
    # Count by status
    status_counts = {}
    for t in trials:
        status = t.get("status", "UNKNOWN")
        status_counts[status] = status_counts.get(status, 0) + 1
    
    print("By status:")
    for status, count in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  {status}: {count:,}")
    print()
    
    # Save to JSON
    output = {
        "generated_at": datetime.now().isoformat(),
        "total_count": len(trials),
        "oncology_count": len(oncology) + len(both),
        "obesity_diabetes_count": len(obesity_diabetes) + len(both),
        "status_breakdown": status_counts,
        "trials": trials,
    }
    
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    
    print(f"Saved to: {OUTPUT_FILE}")
    print()
    print("Next step: Run 02_search_pubmed_targeted.py")


if __name__ == "__main__":
    main()
