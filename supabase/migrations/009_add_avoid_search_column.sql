-- Migration: Add avoid_search column to trials table
-- This allows us to import all trials but exclude certain ones from search/recommendations

-- Add avoid_search column (defaults to false)
ALTER TABLE trials ADD COLUMN IF NOT EXISTS avoid_search BOOLEAN DEFAULT FALSE;

-- Add index for filtering in search/recommendations
CREATE INDEX IF NOT EXISTS idx_trials_avoid_search ON trials(avoid_search);

-- Comment explaining the column
COMMENT ON COLUMN trials.avoid_search IS 'If true, this trial is excluded from search and recommendations. Used for trials without PIs or other quality issues.';
