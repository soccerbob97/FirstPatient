#!/usr/bin/env python3
"""
Step 1: Setup Test Tables

Creates the test embedding table and search function in Supabase.
These are isolated from production tables.

Usage:
    PYTHONPATH=. python scripts/v2_test/01_setup_test_tables.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.db.supabase_client import get_supabase_admin_client


# SQL to create test embedding table (1024 dimensions for Voyage-3.5-lite)
CREATE_TEST_EMBEDDING_TABLE = """
-- Create test embedding table with 1024 dimensions (Voyage-3.5-lite)
CREATE TABLE IF NOT EXISTS trials_embeddings_v2_test (
    id BIGSERIAL PRIMARY KEY,
    trial_id BIGINT NOT NULL REFERENCES trials(id) ON DELETE CASCADE,
    embedding vector(1024),
    embedding_text TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(trial_id)
);

-- Create index for vector search
CREATE INDEX IF NOT EXISTS idx_trials_embeddings_v2_test_embedding 
ON trials_embeddings_v2_test 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Add comment
COMMENT ON TABLE trials_embeddings_v2_test IS 'V2 test embeddings using Voyage-3.5-lite (1024d). Isolated from production.';
"""

# SQL to add new columns to investigators (if not exists)
ADD_INVESTIGATOR_COLUMNS = """
-- Add ORCID and match source columns to investigators
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS orcid_id VARCHAR(20);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_match_source VARCHAR(20);

-- Create index on ORCID ID
CREATE INDEX IF NOT EXISTS idx_investigators_orcid ON investigators(orcid_id) WHERE orcid_id IS NOT NULL;
"""

# SQL to create test search function
CREATE_TEST_SEARCH_FUNCTION = """
-- Test search function using V2 embeddings
CREATE OR REPLACE FUNCTION search_trials_v2_test(
    query_embedding vector(1024),
    match_threshold float DEFAULT 0.5,
    match_count int DEFAULT 20
)
RETURNS TABLE (
    trial_id bigint,
    nct_id varchar,
    brief_title text,
    conditions text[],
    phase varchar,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        t.id as trial_id,
        t.nct_id,
        t.brief_title,
        t.conditions,
        t.phase,
        1 - (e.embedding <=> query_embedding) as similarity
    FROM trials_embeddings_v2_test e
    JOIN trials t ON t.id = e.trial_id
    WHERE 1 - (e.embedding <=> query_embedding) > match_threshold
    ORDER BY e.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;
"""


def main():
    print("🚀 Setting up V2 test tables...")
    
    supabase = get_supabase_admin_client()
    
    # Run migrations via RPC (execute raw SQL)
    print("\n1️⃣ Adding columns to investigators table...")
    try:
        supabase.rpc('exec_sql', {'sql': ADD_INVESTIGATOR_COLUMNS}).execute()
        print("   ✅ Columns added (or already exist)")
    except Exception as e:
        print(f"   ⚠️ Note: {e}")
        print("   You may need to run this SQL manually in Supabase SQL Editor:")
        print("   " + ADD_INVESTIGATOR_COLUMNS.replace('\n', '\n   '))
    
    print("\n2️⃣ Creating test embedding table...")
    try:
        supabase.rpc('exec_sql', {'sql': CREATE_TEST_EMBEDDING_TABLE}).execute()
        print("   ✅ Table created")
    except Exception as e:
        print(f"   ⚠️ Note: {e}")
        print("   You may need to run this SQL manually in Supabase SQL Editor")
    
    print("\n3️⃣ Creating test search function...")
    try:
        supabase.rpc('exec_sql', {'sql': CREATE_TEST_SEARCH_FUNCTION}).execute()
        print("   ✅ Function created")
    except Exception as e:
        print(f"   ⚠️ Note: {e}")
        print("   You may need to run this SQL manually in Supabase SQL Editor")
    
    print("\n" + "="*50)
    print("📋 If any steps failed, run this SQL in Supabase SQL Editor:")
    print("="*50)
    print(ADD_INVESTIGATOR_COLUMNS)
    print(CREATE_TEST_EMBEDDING_TABLE)
    print(CREATE_TEST_SEARCH_FUNCTION)
    print("="*50)
    print("\n✅ Setup complete! Next: run 02_get_subset_trials.py")


if __name__ == "__main__":
    main()
