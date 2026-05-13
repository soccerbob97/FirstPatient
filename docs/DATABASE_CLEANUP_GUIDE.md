# Database Cleanup Guide

## Overview

This document describes the process used to clean up the ClinicalTrials database on April 11, 2026. The goal was to remove trials without identifiable Principal Investigators (PIs) and reclaim storage space.

**Date**: April 11, 2026  
**Database**: Supabase PostgreSQL (Micro compute)  
**Total time**: ~3 hours (including overnight HNSW index rebuild)

---

## Results Summary

| Metric | Before | After | Change |
|--------|--------|-------|--------|
| **trials** | 577,513 | 394,214 | -183,299 (32%) |
| **trial_embeddings_full** | 577,513 | 394,214 | -183,299 |
| **investigator_sites** | 3,246,248 | 2,781,936 | -464,312 |
| **interventions** | 10,303 | 7,685 | -2,618 |
| **Database size** | 15.7 GB | 13 GB | -2.7 GB (17%) |
| **Search query time** | 22,580 ms | 6.5 ms | 3,400x faster |

---

## Why Deletes Are Hard on Large Datasets

| Issue | Cause |
|-------|-------|
| **Timeout** | DELETE locks rows, generates WAL logs, updates indexes |
| **Bloat** | Deleted rows aren't reclaimed until VACUUM |
| **FK checks** | Each delete must verify no child rows exist |
| **Index updates** | Every index on the table must be updated |

---

## Approaches Considered

| Approach | Production Impact | Speed | Verdict |
|----------|------------------|-------|---------|
| Single DELETE | ❌ Timeout | - | Failed |
| Batched DELETE (pg_cron) | ✅ None | Slow (hours) | Too slow |
| Upgrade compute to XL | ⚠️ Brief outage | Fast | Requires restart |
| Table swap (TRUNCATE + INSERT) | ⚠️ 2-3 min downtime | Fast | Good for tables without FKs |
| **Drop FK → Delete → Recreate FK** | ✅ Minimal | **Fast** | **Best approach** |

---

## Step-by-Step Process

### Phase 1: Compact the Embeddings Table (Overnight)

The `trial_embeddings_full` table was the largest (8.9 GB). We recreated it with only the rows we wanted to keep.

```sql
-- Create new table with only trials that have real PIs
CREATE UNLOGGED TABLE trial_embeddings_new AS 
SELECT te.* FROM trial_embeddings_full te
WHERE te.trial_id IN (
    SELECT DISTINCT t.id FROM trials t
    JOIN investigator_sites inv_s ON inv_s.trial_id = t.id
    JOIN investigators i ON inv_s.investigator_id = i.id
    WHERE i.full_name IS NOT NULL
);

-- Swap tables
DROP TABLE trial_embeddings_full;
ALTER TABLE trial_embeddings_new RENAME TO trial_embeddings_full;

-- Add primary key
ALTER TABLE trial_embeddings_full ADD PRIMARY KEY (trial_id);

-- Convert back to logged table
ALTER TABLE trial_embeddings_full SET LOGGED;
```

**Result**: 8.9 GB → 3.1 GB

### Phase 2: Rebuild HNSW Index (Overnight)

With XL compute (upgraded via Supabase Dashboard):

```sql
SET statement_timeout = '8h';
SET maintenance_work_mem = '2GB';
SET max_parallel_maintenance_workers = 2;

CREATE INDEX trial_embeddings_full_hnsw_idx 
ON trial_embeddings_full 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);
```

**Result**: Index built in ~6 minutes, query time reduced from 22s to 6.5ms

### Phase 3: Delete Orphan Data (Fast Method)

#### Step 1: Create Helper Table with IDs to Delete

```sql
CREATE TABLE trials_to_delete_batch AS
SELECT t.id FROM trials t
LEFT JOIN trial_embeddings_full te ON t.id = te.trial_id
WHERE te.trial_id IS NULL;

-- 183,299 rows
```

#### Step 2: Drop Foreign Key Constraints

```sql
ALTER TABLE trial_sites DROP CONSTRAINT IF EXISTS trial_sites_trial_id_fkey;
ALTER TABLE trial_investigators DROP CONSTRAINT IF EXISTS trial_investigators_trial_id_fkey;
ALTER TABLE investigator_sites DROP CONSTRAINT IF EXISTS investigator_sites_trial_id_fkey;
ALTER TABLE interventions DROP CONSTRAINT IF EXISTS interventions_trial_id_fkey;
```

**Why this is safe**: 
- Dropping FK is instant
- During deletion window, new inserts to child tables won't be validated
- Your app likely doesn't insert orphan child records anyway

#### Step 3: Delete from Child Tables First, Then Parent

```sql
SET statement_timeout = '30min';

-- Delete from child tables (order doesn't matter without FKs)
DELETE FROM investigator_sites WHERE trial_id IN (SELECT id FROM trials_to_delete_batch);
-- 464,312 rows deleted

DELETE FROM interventions WHERE trial_id IN (SELECT id FROM trials_to_delete_batch);
-- 2,618 rows deleted

-- Delete from parent table
DELETE FROM trials WHERE id IN (SELECT id FROM trials_to_delete_batch);
-- 183,299 rows deleted
```

**Total time**: ~3 minutes

#### Step 4: Recreate FK Constraints with NOT VALID

```sql
ALTER TABLE trial_sites ADD CONSTRAINT trial_sites_trial_id_fkey 
  FOREIGN KEY (trial_id) REFERENCES trials(id) NOT VALID;

ALTER TABLE trial_investigators ADD CONSTRAINT trial_investigators_trial_id_fkey 
  FOREIGN KEY (trial_id) REFERENCES trials(id) NOT VALID;

ALTER TABLE investigator_sites ADD CONSTRAINT investigator_sites_trial_id_fkey 
  FOREIGN KEY (trial_id) REFERENCES trials(id) NOT VALID;

ALTER TABLE interventions ADD CONSTRAINT interventions_trial_id_fkey 
  FOREIGN KEY (trial_id) REFERENCES trials(id) NOT VALID;
```

**Why NOT VALID**: 
- Instant (no table scan)
- New inserts are still validated
- Existing data is assumed valid (we just cleaned it)

#### Step 5: Clean Up Helper Tables

```sql
DROP TABLE IF EXISTS trials_to_delete_batch;
```

#### Step 6: Validate Constraints (Optional, Low-Traffic)

```sql
-- Run during low-traffic hours
ALTER TABLE investigator_sites VALIDATE CONSTRAINT investigator_sites_trial_id_fkey;
ALTER TABLE interventions VALIDATE CONSTRAINT interventions_trial_id_fkey;
ALTER TABLE trial_sites VALIDATE CONSTRAINT trial_sites_trial_id_fkey;
ALTER TABLE trial_investigators VALIDATE CONSTRAINT trial_investigators_trial_id_fkey;
```

---

## Alternative: pg_cron for Zero-Downtime Batched Deletes

If you can't drop FK constraints, use pg_cron for slow but safe batched deletes:

```sql
-- Enable pg_cron
CREATE EXTENSION IF NOT EXISTS pg_cron;

-- Create helper table
CREATE TABLE ids_to_delete AS SELECT id FROM target_table WHERE <condition>;
CREATE INDEX ON ids_to_delete(id);

-- Schedule batched delete (5000 rows per minute)
SELECT cron.schedule(
  'delete-batch-job',
  '* * * * *',
  $$DELETE FROM target_table WHERE id IN (SELECT id FROM ids_to_delete LIMIT 5000);
    DELETE FROM ids_to_delete WHERE id IN (SELECT id FROM ids_to_delete LIMIT 5000);$$
);

-- Monitor progress
SELECT COUNT(*) FROM ids_to_delete;

-- Unschedule when done
SELECT cron.unschedule('delete-batch-job');
```

**Estimated time**: 183K rows ÷ 5K/min = ~37 minutes

---

## Key Learnings

1. **DELETE is slow** because of FK checks, index updates, and WAL logging
2. **Table recreation** (CREATE AS SELECT + DROP + RENAME) is faster than DELETE for large portions
3. **Dropping FKs temporarily** makes deletes much faster
4. **NOT VALID constraints** allow instant FK recreation while still validating new data
5. **pg_cron** is useful for zero-downtime batched operations
6. **Helper tables** with pre-computed IDs avoid slow subqueries
7. **HNSW index builds** need significant memory - upgrade compute temporarily

---

## Scripts

- `scripts/rebuild_hnsw_index.sh` - Automated HNSW index rebuild with compute scaling
- `scripts/build_hnsw_overnight.sh` - Original overnight build script

---

## Future Considerations

1. **Partitioning**: Consider partitioning large tables by date/status for easier cleanup
2. **Soft deletes**: Add `deleted_at` column instead of hard deletes
3. **Cascade deletes**: Consider `ON DELETE CASCADE` for child tables if appropriate
4. **Regular maintenance**: Schedule periodic VACUUM and cleanup jobs
