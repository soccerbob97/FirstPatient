-- Drop unused raw_json column from trials table
-- This column was intended for storing condensed JSON but is not being used

ALTER TABLE trials DROP COLUMN IF EXISTS raw_json;
