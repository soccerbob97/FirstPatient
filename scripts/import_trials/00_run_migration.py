#!/usr/bin/env python3
"""
Run the migration to add avoid_search column.
Uses postgrest-py to execute raw SQL via Supabase.
"""

import os
from urllib.parse import quote_plus
from dotenv import load_dotenv
import psycopg2

load_dotenv()

# Get database URL from Supabase
# Format: postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Try to construct from SUPABASE_URL and DATABASE_PASSWORD
    supabase_url = os.getenv("SUPABASE_URL", "")
    # Extract project ref from URL like https://xxxx.supabase.co
    if "supabase.co" in supabase_url:
        project_ref = supabase_url.split("//")[1].split(".")[0]
        db_password = os.getenv("DATABASE_PASSWORD", "") or os.getenv("SUPABASE_DB_PASSWORD", "")
        if db_password:
            # URL-encode password to handle special characters like @
            encoded_password = quote_plus(db_password)
            DATABASE_URL = f"postgresql://postgres:{encoded_password}@db.{project_ref}.supabase.co:5432/postgres"

if DATABASE_URL:
    print(f"Connecting to database...")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # Run migration
        print("Adding avoid_search column...")
        cur.execute("""
            ALTER TABLE trials ADD COLUMN IF NOT EXISTS avoid_search BOOLEAN DEFAULT FALSE;
        """)
        
        print("Creating index...")
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_trials_avoid_search ON trials(avoid_search);
        """)
        
        print("Adding comment...")
        cur.execute("""
            COMMENT ON COLUMN trials.avoid_search IS 'If true, this trial is excluded from search and recommendations. Used for trials without PIs or other quality issues.';
        """)
        
        conn.commit()
        print("Migration complete!")
        
        # Verify
        cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = 'trials' AND column_name = 'avoid_search';")
        result = cur.fetchone()
        if result:
            print(f"✓ Column 'avoid_search' exists")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"Error: {e}")
else:
    print("DATABASE_URL not set. Please add to .env:")
    print("  DATABASE_URL=postgresql://postgres:[PASSWORD]@db.[PROJECT_REF].supabase.co:5432/postgres")
    print("")
    print("Or run this SQL manually in Supabase SQL Editor:")
    print("""
ALTER TABLE trials ADD COLUMN IF NOT EXISTS avoid_search BOOLEAN DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS idx_trials_avoid_search ON trials(avoid_search);
COMMENT ON COLUMN trials.avoid_search IS 'If true, this trial is excluded from search and recommendations.';
    """)
