-- Migration: Add ORCID and match source columns to investigators table
-- Run this before using the enrichment script with ORCID integration

-- Add ORCID ID column
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS orcid_id VARCHAR(20);

-- Add match source column to track how the match was made
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_match_source VARCHAR(20);

-- Create index on ORCID ID for lookups
CREATE INDEX IF NOT EXISTS idx_investigators_orcid ON investigators(orcid_id) WHERE orcid_id IS NOT NULL;

-- Add comment for documentation
COMMENT ON COLUMN investigators.orcid_id IS 'ORCID identifier (e.g., 0000-0002-1825-0097)';
COMMENT ON COLUMN investigators.s2_match_source IS 'How the S2 match was made: orcid, s2_affiliation, or s2_topics';
