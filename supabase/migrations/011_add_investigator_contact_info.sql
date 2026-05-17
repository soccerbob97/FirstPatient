-- Add contact info columns to investigators table
-- These fields come from site-level contacts in ClinicalTrials.gov data

ALTER TABLE investigators 
ADD COLUMN IF NOT EXISTS email VARCHAR(255),
ADD COLUMN IF NOT EXISTS phone VARCHAR(50);

-- Index for email lookups
CREATE INDEX IF NOT EXISTS idx_investigators_email ON investigators(email) WHERE email IS NOT NULL;

-- Comment explaining the data source
COMMENT ON COLUMN investigators.email IS 'Contact email from ClinicalTrials.gov location.contacts';
COMMENT ON COLUMN investigators.phone IS 'Contact phone from ClinicalTrials.gov location.contacts';
