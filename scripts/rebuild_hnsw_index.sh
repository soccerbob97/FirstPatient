#!/bin/bash
#
# Rebuild HNSW Index Script
# 
# This script rebuilds the HNSW index on trial_embeddings_full table.
# It handles compute scaling (Micro -> XL -> Micro) automatically.
#
# Usage: ./rebuild_hnsw_index.sh
#

set -e

# Load environment variables
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -f "$PROJECT_DIR/.env" ]; then
    export $(grep -v '^#' "$PROJECT_DIR/.env" | xargs)
fi

# Configuration
SUPABASE_PROJECT_REF="zwcreraudeemddmloeul"
SUPABASE_DB_HOST="db.${SUPABASE_PROJECT_REF}.supabase.co"
SUPABASE_DB_USER="postgres"
SUPABASE_DB_PASSWORD="${DATABASE_PASSWORD:-BoostHealth@3000}"
SUPABASE_DB_NAME="postgres"

# Compute sizes
COMPUTE_MICRO="ci_micro"
COMPUTE_XL="ci_xlarge"
TARGET_COMPUTE="$COMPUTE_XL"

# PSQL command
export PGPASSWORD="$SUPABASE_DB_PASSWORD"
PSQL="/opt/homebrew/opt/libpq/bin/psql -h $SUPABASE_DB_HOST -p 5432 -U $SUPABASE_DB_USER -d $SUPABASE_DB_NAME"

# Log file
LOG_FILE="$PROJECT_DIR/logs/hnsw_rebuild_$(date +%Y%m%d_%H%M%S).log"
mkdir -p "$PROJECT_DIR/logs"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

upgrade_compute() {
    local target=$1
    log "Upgrading compute to $target..."
    
    response=$(curl -s -X PATCH "https://api.supabase.com/v1/projects/$SUPABASE_PROJECT_REF" \
        -H "Authorization: Bearer $SUPABASE_ACCESS_TOKEN" \
        -H "Content-Type: application/json" \
        -d "{\"name\": \"ClinicalTrials\", \"addon_variants\": {\"compute_instance\": \"$target\"}}")
    
    log "API Response: $response"
    
    log "Waiting 60 seconds for compute change to propagate..."
    sleep 60
    
    # Verify by checking shared_buffers
    shared_buffers=$($PSQL -t -c "SHOW shared_buffers;" 2>/dev/null | tr -d ' ')
    log "Current shared_buffers: $shared_buffers"
    
    # Note: If shared_buffers hasn't changed, the script will still work
    # but will use less memory and take longer
}

check_index_exists() {
    $PSQL -t -c "SELECT COUNT(*) FROM pg_indexes WHERE indexname = 'trial_embeddings_full_hnsw_idx';" 2>/dev/null | tr -d ' '
}

build_hnsw_index() {
    log "Building HNSW index on trial_embeddings_full..."
    log "This may take 30-120 minutes depending on compute size and memory."
    
    # Drop existing index if any
    $PSQL -c "DROP INDEX IF EXISTS trial_embeddings_full_hnsw_idx;" 2>/dev/null || true
    
    # Check available memory and set maintenance_work_mem accordingly
    shared_buffers=$($PSQL -t -c "SHOW shared_buffers;" 2>/dev/null | tr -d ' ')
    log "Current shared_buffers: $shared_buffers"
    
    # Determine maintenance_work_mem based on compute size
    # XL (4GB shared_buffers) -> 2GB, Medium (1GB) -> 512MB, Micro (256MB) -> 128MB
    case "$shared_buffers" in
        4GB|4096MB) mem="2GB" ;;
        1GB|1024MB) mem="512MB" ;;
        *) mem="128MB" ;;
    esac
    log "Setting maintenance_work_mem to $mem"
    
    # Build index - this will take longer with less memory but will complete
    $PSQL << EOF
SET statement_timeout = '8h';
SET maintenance_work_mem = '$mem';
SET max_parallel_maintenance_workers = 2;

CREATE INDEX trial_embeddings_full_hnsw_idx 
ON trial_embeddings_full 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
EOF
    exit_code=$?
    
    if [ $exit_code -eq 0 ]; then
        log "HNSW index created successfully!"
        return 0
    else
        log "ERROR: Failed to create HNSW index (exit code: $exit_code)"
        return 1
    fi
}

verify_index() {
    log "Verifying index..."
    
    $PSQL << 'EOF'
-- Check index exists and size
SELECT 
    indexname,
    pg_size_pretty(pg_relation_size(quote_ident(indexname)::regclass)) as index_size
FROM pg_indexes 
WHERE tablename = 'trial_embeddings_full';

-- Test query performance
EXPLAIN ANALYZE
SELECT trial_id 
FROM trial_embeddings_full 
ORDER BY embedding <=> (SELECT embedding FROM trial_embeddings_full LIMIT 1)
LIMIT 10;
EOF
}

# Main execution
log "=============================================="
log "HNSW Index Rebuild Script Started"
log "=============================================="

# Check current state
row_count=$($PSQL -t -c "SELECT COUNT(*) FROM trial_embeddings_full;" 2>/dev/null | tr -d ' ')
log "Current row count: $row_count"

index_exists=$(check_index_exists)
log "HNSW index exists: $index_exists"

# Step 1: Build HNSW index
log ""
log "[STEP 1/3] Building HNSW index..."
if build_hnsw_index; then
    log "Index build completed!"
else
    log "Index build failed. Check logs for details."
    exit 1
fi

# Step 2: Verify index
log ""
log "[STEP 2/3] Verifying index..."
verify_index

# Step 3: Downgrade compute back to Micro
log ""
log "[STEP 3/3] Downgrading compute back to Micro..."
upgrade_compute "$COMPUTE_MICRO"

log ""
log "=============================================="
log "HNSW Index Rebuild COMPLETED"
log "=============================================="
log ""
log "Summary:"
log "  - Rows indexed: $row_count"
log "  - Index: trial_embeddings_full_hnsw_idx"
log "  - Compute: Back to Micro"
log ""
log "Log file: $LOG_FILE"
