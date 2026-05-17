# Investigator Merge Procedure

## Overview
This document describes the correct procedure for merging duplicate investigator records in the database. **Following this procedure is critical to avoid data loss.**

## Database Schema
Tables that reference `investigators.id`:
- `trial_investigators` - Links investigators to trials (UNIQUE: trial_id, investigator_id)
- `investigator_sites` - Links investigators to sites (UNIQUE: investigator_id, site_id, trial_id, link_type)
- `investigator_metrics` - Pre-computed metrics per investigator

## ⚠️ CRITICAL: What NOT To Do

**NEVER run DELETE on trial_investigators/investigator_sites before UPDATE.**

This will permanently delete trial/site connections:
```sql
-- ❌ WRONG - This deletes data permanently!
DELETE FROM trial_investigators WHERE investigator_id IN (duplicate_ids);
```

## ✅ Correct Merge Procedure

### Step 1: Identify Primary and Duplicates
```sql
SELECT id, full_name, affiliation,
       (SELECT COUNT(*) FROM trial_investigators ti WHERE ti.investigator_id = i.id) as trial_count
FROM investigators i
WHERE full_name ILIKE '%Name Here%'
ORDER BY trial_count DESC;
```
- **Primary ID** = The one with the most trials (first row)
- **Duplicate IDs** = All other rows

### Step 2: Use apply_migration (NOT execute_sql)

Always use `apply_migration` for merge operations. This ensures atomicity.

```sql
-- =============================================
-- MERGE [INVESTIGATOR NAME] (Primary: [PRIMARY_ID])
-- Duplicates: [DUPLICATE_IDS]
-- =============================================

-- Step 2a: Update trial_investigators - move links to primary
-- The NOT EXISTS prevents unique constraint violations
UPDATE trial_investigators SET investigator_id = [PRIMARY_ID]
WHERE investigator_id IN ([DUPLICATE_IDS])
  AND NOT EXISTS (
    SELECT 1 FROM trial_investigators t2 
    WHERE t2.trial_id = trial_investigators.trial_id 
      AND t2.investigator_id = [PRIMARY_ID]
  );

-- Step 2b: Delete remaining duplicates (ones that would violate unique constraint)
DELETE FROM trial_investigators WHERE investigator_id IN ([DUPLICATE_IDS]);

-- Step 2c: Update investigator_sites - move links to primary
UPDATE investigator_sites SET investigator_id = [PRIMARY_ID]
WHERE investigator_id IN ([DUPLICATE_IDS])
  AND NOT EXISTS (
    SELECT 1 FROM investigator_sites t2 
    WHERE t2.site_id = investigator_sites.site_id 
      AND t2.trial_id = investigator_sites.trial_id 
      AND t2.link_type = investigator_sites.link_type 
      AND t2.investigator_id = [PRIMARY_ID]
  );

-- Step 2d: Delete remaining site duplicates
DELETE FROM investigator_sites WHERE investigator_id IN ([DUPLICATE_IDS]);

-- Step 2e: Delete from investigator_metrics
DELETE FROM investigator_metrics WHERE investigator_id IN ([DUPLICATE_IDS]);

-- Step 2f: Delete duplicate investigators
DELETE FROM investigators WHERE id IN ([DUPLICATE_IDS]);
```

### Step 3: Verify the Merge
```sql
SELECT i.id, i.full_name, 
       (SELECT COUNT(*) FROM trial_investigators ti WHERE ti.investigator_id = i.id) as trial_count,
       (SELECT COUNT(*) FROM investigator_sites isites WHERE isites.investigator_id = i.id) as site_count
FROM investigators i
WHERE i.id = [PRIMARY_ID];
```

## Incident Log

### May 15, 2026 - Ye Guo Data Loss
- **What happened**: Used `execute_sql` with DELETE statements instead of `apply_migration` with UPDATE-then-DELETE
- **Result**: Lost ~40 trial connections for Ye Guo (went from ~53 trials to 13)
- **Root cause**: Ran DELETE queries directly without first running UPDATE to preserve connections
- **Lesson**: Always use the full migration pattern with UPDATE before DELETE

### May 15, 2026 - Successful Merges
- Josep Tabernero: 17 duplicates → 1 record (18 trials) ✅
- Mark Ratain: 6 duplicates → 1 record (7 trials) ✅
- Kyriakos Papadopoulos: 3 duplicates → 1 record (2 trials) ✅

## Future Improvements
1. Create a stored procedure for investigator merges
2. Add a backup step before any merge operation
3. Consider adding a "merged_into" column to track merge history instead of deleting
