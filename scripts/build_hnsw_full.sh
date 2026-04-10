#!/bin/bash
# =============================================================================
# FULL HNSW INDEX BUILD SCRIPT (WITH AUTO COMPUTE SCALING)
# =============================================================================
# This script:
# 1. Upgrades Supabase compute to Medium (4GB RAM)
# 2. Builds HNSW index on all 577K trial embeddings
# 3. Downgrades compute back to Micro when done
#
# PREREQUISITES:
# - Set SUPABASE_ACCESS_TOKEN environment variable (from dashboard)
# - Ensure spend cap is disabled in Supabase billing
#
# Run with: caffeinate -i ./scripts/build_hnsw_full.sh
# =============================================================================

set -e  # Exit on error

# =============================================================================
# CONFIGURATION
# =============================================================================

# Load environment variables from .env file
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
    echo "Loaded environment from $PROJECT_DIR/.env"
fi

SUPABASE_PROJECT_REF="zwcreraudeemddmloeul"
SUPABASE_ACCESS_TOKEN="${SUPABASE_ACCESS_TOKEN:-}"

# Database connection
export PGPASSWORD='BoostHealth@3000'
DB_HOST="db.zwcreraudeemddmloeul.supabase.co"
DB_PORT="5432"
DB_USER="postgres"
DB_NAME="postgres"
PSQL="/opt/homebrew/opt/libpq/bin/psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME"

# Compute sizes (Supabase addon variants)
COMPUTE_MICRO="ci_micro"
COMPUTE_SMALL="ci_small"
COMPUTE_MEDIUM="ci_medium"
TARGET_COMPUTE="ci_xlarge"  # XL has 16GB RAM, can fit all 577K vectors in memory

# Safety thresholds
MAX_DB_SIZE_GB=30

# Logging
LOG_FILE="hnsw_full_build_$(date +%Y%m%d_%H%M%S).log"
exec > >(tee -a "$LOG_FILE") 2>&1

echo "=============================================="
echo "FULL HNSW Index Build Started: $(date)"
echo "Log file: $LOG_FILE"
echo "Target compute: $TARGET_COMPUTE"
echo "=============================================="

# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

check_access_token() {
    if [ -z "$SUPABASE_ACCESS_TOKEN" ]; then
        echo ""
        echo "ERROR: SUPABASE_ACCESS_TOKEN not set!"
        echo ""
        echo "To get your access token:"
        echo "1. Go to https://supabase.com/dashboard/account/tokens"
        echo "2. Generate a new access token"
        echo "3. Run: export SUPABASE_ACCESS_TOKEN='your-token-here'"
        echo "4. Then re-run this script"
        echo ""
        exit 1
    fi
}

upgrade_compute() {
    local target_size="$1"
    echo "[COMPUTE] Upgrading to $target_size..."
    
    response=$(curl -s -X PATCH \
        "https://api.supabase.com/v1/projects/${SUPABASE_PROJECT_REF}/billing/addons" \
        -H "Authorization: Bearer ${SUPABASE_ACCESS_TOKEN}" \
        -H "Content-Type: application/json" \
        -d "{\"addon_type\": \"compute_instance\", \"addon_variant\": \"${target_size}\"}")
    
    echo "[COMPUTE] Response: $response"
    
    # Wait for compute to be ready (restart takes ~1-2 minutes)
    echo "[COMPUTE] Waiting 120 seconds for compute upgrade to complete..."
    sleep 120
    
    # Verify connection works
    echo "[COMPUTE] Verifying database connection..."
    if $PSQL -c "SELECT 1;" > /dev/null 2>&1; then
        echo "[COMPUTE] Database connection verified!"
    else
        echo "[COMPUTE] WARNING: Database connection failed, waiting another 60 seconds..."
        sleep 60
    fi
}

downgrade_compute() {
    echo "[COMPUTE] Downgrading back to Micro..."
    
    # Remove the compute addon to revert to default (Micro)
    response=$(curl -s -X DELETE \
        "https://api.supabase.com/v1/projects/${SUPABASE_PROJECT_REF}/billing/addons/compute_instance" \
        -H "Authorization: Bearer ${SUPABASE_ACCESS_TOKEN}")
    
    echo "[COMPUTE] Downgrade response: $response"
    echo "[COMPUTE] Compute will restart. Index is preserved."
}

check_disk_size() {
    local step_name="$1"
    echo "[SAFETY] Checking disk size before: $step_name"
    
    local db_size_bytes=$($PSQL -t -A -c "SELECT pg_database_size('postgres');" 2>/dev/null)
    
    if [ -z "$db_size_bytes" ]; then
        echo "[WARNING] Could not get database size, continuing..."
        return 0
    fi
    
    local db_size_gb=$(echo "scale=2; $db_size_bytes / 1024 / 1024 / 1024" | bc)
    echo "[SAFETY] Current DB size: ${db_size_gb} GB (threshold: ${MAX_DB_SIZE_GB} GB)"
    
    if (( $(echo "$db_size_gb > $MAX_DB_SIZE_GB" | bc -l) )); then
        echo ""
        echo "!!! SAFETY ALERT: DATABASE SIZE EXCEEDED ${MAX_DB_SIZE_GB} GB !!!"
        echo "Initiating cleanup and downgrade..."
        
        $PSQL -c "DROP TABLE IF EXISTS trial_embeddings_full CASCADE;" 2>/dev/null || true
        downgrade_compute
        exit 1
    fi
    
    return 0
}

cleanup_on_error() {
    echo ""
    echo "!!! ERROR DETECTED - CLEANING UP !!!"
    echo "Attempting to downgrade compute..."
    downgrade_compute
    exit 1
}

# Trap errors to ensure we downgrade compute
trap cleanup_on_error ERR

# =============================================================================
# MAIN SCRIPT
# =============================================================================

# Step 0: Check prerequisites
check_access_token

# Step 1: Upgrade compute
echo ""
echo "=============================================="
echo "[STEP 1/7] Upgrading compute to $TARGET_COMPUTE"
echo "=============================================="
upgrade_compute "$TARGET_COMPUTE"

# Verify new settings
echo "[STEP 1/7] Checking new memory settings..."
$PSQL -c "SELECT name, setting, unit FROM pg_settings WHERE name IN ('maintenance_work_mem', 'shared_buffers', 'max_parallel_maintenance_workers');"

# Step 2: Create unlogged table
check_disk_size "Step 2 - Create table"
echo ""
echo "=============================================="
echo "[STEP 2/7] Creating unlogged table..."
echo "Started: $(date)"
echo "=============================================="

$PSQL << 'EOF'
SET statement_timeout = '0';
DROP TABLE IF EXISTS trial_embeddings_full;
CREATE UNLOGGED TABLE trial_embeddings_full (
    trial_id BIGINT PRIMARY KEY,
    embedding vector(1536) NOT NULL
);
SELECT 'Table created' as status;
EOF

echo "Completed: $(date)"

# Step 3: Copy all embeddings (no filtering - include all trials with embeddings)
check_disk_size "Step 3 - Copy embeddings"
echo ""
echo "=============================================="
echo "[STEP 3/7] Copying all embeddings (~577K rows)..."
echo "Estimated time: 30-60 minutes"
echo "Started: $(date)"
echo "=============================================="

$PSQL << 'EOF'
SET statement_timeout = '0';

INSERT INTO trial_embeddings_full (trial_id, embedding)
SELECT id, embedding
FROM trials
WHERE embedding IS NOT NULL;

SELECT 'Rows inserted: ' || COUNT(*)::text as status FROM trial_embeddings_full;
EOF

echo "Completed: $(date)"

# Step 4: Build HNSW index (the main event!)
check_disk_size "Step 4 - Build HNSW index"
echo ""
echo "=============================================="
echo "[STEP 4/7] Building HNSW index..."
echo "This is the longest step - estimated 2-6 hours"
echo "Started: $(date)"
echo "=============================================="

$PSQL << 'EOF'
SET statement_timeout = '0';
SET maintenance_work_mem = '2GB';
SET max_parallel_maintenance_workers = 4;

CREATE INDEX trial_embeddings_full_hnsw_idx 
ON trial_embeddings_full 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

SELECT 'HNSW index created' as status;
EOF

echo "Completed: $(date)"

# Step 5: Convert to logged table
check_disk_size "Step 5 - Convert to logged"
echo ""
echo "=============================================="
echo "[STEP 5/7] Converting to logged table..."
echo "Estimated time: 30-60 minutes"
echo "Started: $(date)"
echo "=============================================="

$PSQL << 'EOF'
SET statement_timeout = '0';
SET maintenance_work_mem = '2GB';

ALTER TABLE trial_embeddings_full SET LOGGED;

SELECT 'Table converted to logged' as status;
EOF

echo "Completed: $(date)"

# Step 6: Update search function
echo ""
echo "=============================================="
echo "[STEP 6/7] Updating search function..."
echo "Started: $(date)"
echo "=============================================="

$PSQL << 'EOF'
SET statement_timeout = '5min';

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

# Step 7: Downgrade compute and verify
echo ""
echo "=============================================="
echo "[STEP 7/7] Downgrading compute and verifying..."
echo "=============================================="

# Verify before downgrade
$PSQL << 'EOF'
SELECT 
    'trial_embeddings_full' as table_name,
    COUNT(*) as row_count,
    pg_size_pretty(pg_total_relation_size('trial_embeddings_full')) as total_size
FROM trial_embeddings_full;

SELECT indexname, pg_size_pretty(pg_relation_size(quote_ident(indexname)::regclass)) as index_size
FROM pg_indexes 
WHERE tablename = 'trial_embeddings_full';

SELECT pg_size_pretty(pg_database_size('postgres')) as total_db_size;
EOF

# Downgrade compute
downgrade_compute

echo ""
echo "=============================================="
echo "HNSW Index Build COMPLETED: $(date)"
echo "=============================================="
echo ""
echo "Summary:"
echo "- Full HNSW index built on ~577K trials"
echo "- Compute downgraded back to Micro"
echo "- Index persists after downgrade"
echo ""
echo "Next steps:"
echo "1. Test the search in your app"
echo "2. Optionally drop the demo table:"
echo "   DROP TABLE IF EXISTS trial_embeddings_demo;"
echo ""
