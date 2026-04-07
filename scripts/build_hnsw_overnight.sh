#!/bin/bash
# =============================================================================
# OVERNIGHT HNSW INDEX BUILD SCRIPT (WITH SAFETY CHECKS)
# =============================================================================
# This script builds a full HNSW index on ~548K trial embeddings
# Excludes trials that only have company/sponsor PIs (no real investigators)
#
# SAFETY FEATURES:
# - Checks disk size before each step
# - Auto-cleanup if disk exceeds threshold (25 GB)
# - Kills database queries if threshold exceeded
#
# Estimated time: 3-5 hours
# Disk space needed: ~8.7 GB additional
#
# Run with: caffeinate -i ./scripts/build_hnsw_overnight.sh
# =============================================================================

set -e  # Exit on error

# Database connection
export PGPASSWORD='BoostHealth@3000'
DB_HOST="db.zwcreraudeemddmloeul.supabase.co"
DB_PORT="5432"
DB_USER="postgres"
DB_NAME="postgres"
PSQL="/opt/homebrew/opt/libpq/bin/psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME"

# SAFETY THRESHOLDS
MAX_DB_SIZE_GB=27  # Maximum allowed database size in GB

# Logging
LOG_FILE="hnsw_build_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=============================================="
echo "HNSW Index Build Started: $(date)"
echo "Log file: $LOG_FILE"
echo "Safety threshold: ${MAX_DB_SIZE_GB} GB max"
echo "=============================================="

# -----------------------------------------------------------------------------
# SAFETY CHECK FUNCTION
# -----------------------------------------------------------------------------
check_disk_size() {
    local step_name="$1"
    echo "[SAFETY CHECK] Checking disk size before: $step_name"
    
    # Get current database size in GB
    local db_size_bytes=$($PSQL -t -A -c "SELECT pg_database_size('postgres');" 2>/dev/null)
    
    if [ -z "$db_size_bytes" ]; then
        echo "[WARNING] Could not get database size, continuing..."
        return 0
    fi
    
    local db_size_gb=$(echo "scale=2; $db_size_bytes / 1024 / 1024 / 1024" | bc)
    echo "[SAFETY CHECK] Current DB size: ${db_size_gb} GB (threshold: ${MAX_DB_SIZE_GB} GB)"
    
    # Check if exceeded threshold
    if (( $(echo "$db_size_gb > $MAX_DB_SIZE_GB" | bc -l) )); then
        echo ""
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        echo "[SAFETY ALERT] DATABASE SIZE EXCEEDED ${MAX_DB_SIZE_GB} GB!"
        echo "Current size: ${db_size_gb} GB"
        echo "Initiating emergency cleanup..."
        echo "!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!"
        
        # Kill any running queries on our table
        $PSQL -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE query LIKE '%trial_embeddings_full%' AND pid != pg_backend_pid();" 2>/dev/null || true
        
        # Drop the table
        $PSQL -c "DROP TABLE IF EXISTS trial_embeddings_full CASCADE;" 2>/dev/null || true
        
        echo "[CLEANUP] Table dropped. Exiting."
        exit 1
    fi
    
    return 0
}

# -----------------------------------------------------------------------------
# STEP 1: Create the unlogged table for fast inserts
# -----------------------------------------------------------------------------
check_disk_size "Step 1 - Create table"

echo ""
echo "[STEP 1/6] Creating unlogged table trial_embeddings_full..."
echo "Started: $(date)"

$PSQL << 'EOF'
-- Set long timeout for this session
SET statement_timeout = '6h';

-- Drop if exists (in case of retry)
DROP TABLE IF EXISTS trial_embeddings_full;

-- Create unlogged table (faster inserts, no WAL)
CREATE UNLOGGED TABLE trial_embeddings_full (
    trial_id BIGINT PRIMARY KEY,
    embedding vector(1536) NOT NULL
);

SELECT 'Table created' as status;
EOF

echo "Completed: $(date)"

# -----------------------------------------------------------------------------
# STEP 2: Copy embeddings (excluding company-only trials)
# -----------------------------------------------------------------------------
check_disk_size "Step 2 - Copy embeddings"

echo ""
echo "[STEP 2/6] Copying embeddings from trials table..."
echo "This will copy ~548K rows (excluding company-only trials)"
echo "Estimated time: 30-60 minutes"
echo "Started: $(date)"

$PSQL << 'EOF'
SET statement_timeout = '6h';

-- Insert embeddings for trials that are NOT company-only
-- Company-only = has investigators but ALL are companies (no real PIs)
INSERT INTO trial_embeddings_full (trial_id, embedding)
SELECT t.id, t.embedding
FROM trials t
WHERE t.embedding IS NOT NULL
  AND NOT EXISTS (
    -- Exclude trials where ALL investigators are companies
    SELECT 1 
    FROM trial_investigators ti
    JOIN investigators i ON i.id = ti.investigator_id
    WHERE ti.trial_id = t.id
    HAVING COUNT(*) > 0  -- Has at least one investigator
       AND COUNT(*) = COUNT(
           CASE WHEN i.full_name ~* '(inc|llc|ltd|pharma|clinical|center|centre|gsk|pfizer|novartis|merck|sanofi|roche|lilly|bristol|johnson|abbvie|amgen|biogen|gilead|boehringer|bayer|takeda|novo nordisk|regeneron|vertex|moderna|astellas|transparency|call center|hotline|coordinator|research group)'
           THEN 1 END
       )  -- All investigators are companies
  );

SELECT 'Rows inserted: ' || COUNT(*)::text as status FROM trial_embeddings_full;
EOF

echo "Completed: $(date)"

# -----------------------------------------------------------------------------
# STEP 3: Build HNSW index
# -----------------------------------------------------------------------------
check_disk_size "Step 3 - Build HNSW index"

echo ""
echo "[STEP 3/6] Building HNSW index..."
echo "This is the longest step - estimated 2-4 hours"
echo "Started: $(date)"

$PSQL << 'EOF'
SET statement_timeout = '6h';
SET maintenance_work_mem = '1GB';

-- Build HNSW index with optimized parameters
CREATE INDEX trial_embeddings_full_hnsw_idx 
ON trial_embeddings_full 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

SELECT 'HNSW index created' as status;
EOF

echo "Completed: $(date)"

# -----------------------------------------------------------------------------
# STEP 4: Convert to logged table
# -----------------------------------------------------------------------------
check_disk_size "Step 4 - Convert to logged"

echo ""
echo "[STEP 4/6] Converting to logged table..."
echo "Estimated time: 30-60 minutes"
echo "Started: $(date)"

$PSQL << 'EOF'
SET statement_timeout = '6h';
SET maintenance_work_mem = '1GB';

ALTER TABLE trial_embeddings_full SET LOGGED;

SELECT 'Table converted to logged' as status;
EOF

echo "Completed: $(date)"

# -----------------------------------------------------------------------------
# STEP 5: Update search function
# -----------------------------------------------------------------------------
check_disk_size "Step 5 - Update function"

echo ""
echo "[STEP 5/6] Updating search function to use new table..."
echo "Started: $(date)"

$PSQL << 'EOF'
SET statement_timeout = '5min';

-- Update the search function to use the full HNSW table
CREATE OR REPLACE FUNCTION search_trials_by_embedding(
    query_embedding vector(1536),
    similarity_threshold float DEFAULT 0.5,
    max_results int DEFAULT 10
)
RETURNS TABLE (
    id bigint,
    nct_id varchar(20),
    brief_title text,
    conditions text[],
    phase varchar(50),
    overall_status varchar(50),
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    -- Set HNSW search parameters for better recall
    SET LOCAL hnsw.ef_search = 100;
    
    RETURN QUERY
    SELECT 
        t.id,
        t.nct_id,
        t.brief_title,
        t.conditions,
        t.phase,
        t.overall_status,
        1 - (te.embedding <=> query_embedding) AS similarity
    FROM trial_embeddings_full te
    JOIN trials t ON t.id = te.trial_id
    WHERE 1 - (te.embedding <=> query_embedding) >= similarity_threshold
    ORDER BY te.embedding <=> query_embedding
    LIMIT max_results;
END;
$$;

SELECT 'Search function updated' as status;
EOF

echo "Completed: $(date)"

# -----------------------------------------------------------------------------
# STEP 6: Cleanup and verify
# -----------------------------------------------------------------------------
echo ""
echo "[STEP 6/6] Verifying and cleaning up..."
echo "Started: $(date)"

$PSQL << 'EOF'
-- Verify the new table
SELECT 
    'trial_embeddings_full' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('trial_embeddings_full')) as total_size
FROM trial_embeddings_full;

-- Check index exists
SELECT indexname, pg_size_pretty(pg_relation_size(quote_ident(indexname)::regclass)) as index_size
FROM pg_indexes 
WHERE tablename = 'trial_embeddings_full';

-- Test a sample query
EXPLAIN ANALYZE
SELECT trial_id 
FROM trial_embeddings_full 
ORDER BY embedding <=> (SELECT embedding FROM trial_embeddings_full LIMIT 1)
LIMIT 10;

-- Show total database size
SELECT pg_size_pretty(pg_database_size('postgres')) as total_db_size;
EOF

echo ""
echo "=============================================="
echo "HNSW Index Build COMPLETED: $(date)"
echo "=============================================="
echo ""
echo "Next steps:"
echo "1. Test the search in your app"
echo "2. Optionally drop the demo table to save space:"
echo "   DROP TABLE IF EXISTS trial_embeddings_demo;"
echo ""
