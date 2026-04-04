-- Clinical Trial Site Recommender - Initial Schema
-- Run this in Supabase SQL Editor or as a migration

-- ============================================
-- EXTENSIONS
-- ============================================
CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- Fuzzy text matching

-- ============================================
-- CORE TABLES
-- ============================================

-- Trials: clinical trial metadata from ClinicalTrials.gov
CREATE TABLE IF NOT EXISTS trials (
    id BIGSERIAL PRIMARY KEY,
    nct_id VARCHAR(20) UNIQUE NOT NULL,
    
    -- Titles
    brief_title TEXT,
    official_title TEXT,
    
    -- Description
    brief_summary TEXT,
    
    -- Conditions (array for multi-condition trials)
    conditions TEXT[],
    
    -- Trial design
    phase VARCHAR(50),
    study_type VARCHAR(50),
    
    -- Status
    overall_status VARCHAR(50),
    start_date DATE,
    completion_date DATE,
    primary_completion_date DATE,
    
    -- Enrollment
    enrollment INTEGER,
    enrollment_type VARCHAR(20),
    
    -- Sponsor
    lead_sponsor_name VARCHAR(500),
    lead_sponsor_class VARCHAR(50),
    
    -- Dates
    last_update_posted DATE,
    
    -- Raw JSON (for fields we might need later)
    raw_json JSONB,
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Sites: clinical trial locations/facilities
CREATE TABLE IF NOT EXISTS sites (
    id BIGSERIAL PRIMARY KEY,
    
    -- Facility
    facility_name VARCHAR(500),
    facility_name_normalized VARCHAR(500),
    
    -- Location
    city VARCHAR(100),
    state VARCHAR(100),
    country VARCHAR(100),
    zip VARCHAR(20),
    
    -- Classification (to be enriched later)
    institution_type VARCHAR(50),
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(facility_name, city, country)
);

-- Investigators: PIs and other study officials
CREATE TABLE IF NOT EXISTS investigators (
    id BIGSERIAL PRIMARY KEY,
    
    -- Name
    full_name VARCHAR(255) NOT NULL,
    name_normalized VARCHAR(255),
    
    -- Role from CT.gov
    role VARCHAR(100),
    
    -- Affiliation as listed
    affiliation VARCHAR(500),
    affiliation_normalized VARCHAR(500),
    
    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(full_name, affiliation)
);

-- ============================================
-- JUNCTION TABLES
-- ============================================

-- Trial <-> Site relationship
CREATE TABLE IF NOT EXISTS trial_sites (
    id BIGSERIAL PRIMARY KEY,
    trial_id BIGINT NOT NULL REFERENCES trials(id) ON DELETE CASCADE,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    
    recruitment_status VARCHAR(50),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(trial_id, site_id)
);

-- Trial <-> Investigator relationship
CREATE TABLE IF NOT EXISTS trial_investigators (
    id BIGSERIAL PRIMARY KEY,
    trial_id BIGINT NOT NULL REFERENCES trials(id) ON DELETE CASCADE,
    investigator_id BIGINT NOT NULL REFERENCES investigators(id) ON DELETE CASCADE,
    
    role VARCHAR(100),
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(trial_id, investigator_id)
);

-- Investigator <-> Site linkage (derived from trial data)
CREATE TABLE IF NOT EXISTS investigator_sites (
    id BIGSERIAL PRIMARY KEY,
    investigator_id BIGINT NOT NULL REFERENCES investigators(id) ON DELETE CASCADE,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    trial_id BIGINT REFERENCES trials(id) ON DELETE CASCADE,  -- Which trial established this link
    
    -- Type of relationship
    link_type VARCHAR(50) NOT NULL,  -- 'oversight' | 'affiliation_match' | 'site_contact'
    -- oversight: overall official linked to all trial sites (study-level responsibility)
    -- affiliation_match: PI's affiliation matches site facility name
    -- site_contact: explicitly listed in location.contacts
    
    -- Confidence score for heuristic matches
    link_confidence DECIMAL(3,2),  -- 0.00 to 1.00 (null for explicit links)
    
    created_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(investigator_id, site_id, trial_id, link_type)
);

-- ============================================
-- METRICS TABLES (computed/derived)
-- ============================================

-- Investigator performance metrics by indication
CREATE TABLE IF NOT EXISTS investigator_metrics (
    id BIGSERIAL PRIMARY KEY,
    investigator_id BIGINT NOT NULL REFERENCES investigators(id) ON DELETE CASCADE,
    
    -- Scope (null = overall, otherwise specific indication)
    indication VARCHAR(255),
    
    -- Counts
    total_trials INTEGER DEFAULT 0,
    completed_trials INTEGER DEFAULT 0,
    active_trials INTEGER DEFAULT 0,
    
    -- Rates
    completion_rate DECIMAL(5,4),
    
    -- Timing
    avg_trial_duration_days INTEGER,
    last_trial_date DATE,
    
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(investigator_id, indication)
);

-- Site performance metrics by indication
CREATE TABLE IF NOT EXISTS site_metrics (
    id BIGSERIAL PRIMARY KEY,
    site_id BIGINT NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
    
    indication VARCHAR(255),
    
    total_trials INTEGER DEFAULT 0,
    completed_trials INTEGER DEFAULT 0,
    active_trials INTEGER DEFAULT 0,
    
    completion_rate DECIMAL(5,4),
    avg_trial_duration_days INTEGER,
    last_trial_date DATE,
    
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    
    UNIQUE(site_id, indication)
);

-- ============================================
-- INDEXES
-- ============================================

-- Trials
CREATE INDEX idx_trials_nct_id ON trials(nct_id);
CREATE INDEX idx_trials_phase ON trials(phase);
CREATE INDEX idx_trials_status ON trials(overall_status);
CREATE INDEX idx_trials_conditions ON trials USING GIN(conditions);
CREATE INDEX idx_trials_sponsor ON trials(lead_sponsor_name);

-- Sites
CREATE INDEX idx_sites_country ON sites(country);
CREATE INDEX idx_sites_facility_trgm ON sites USING GIN(facility_name_normalized gin_trgm_ops);

-- Investigators
CREATE INDEX idx_investigators_name_trgm ON investigators USING GIN(name_normalized gin_trgm_ops);
CREATE INDEX idx_investigators_affiliation_trgm ON investigators USING GIN(affiliation_normalized gin_trgm_ops);

-- Junction tables
CREATE INDEX idx_trial_sites_trial ON trial_sites(trial_id);
CREATE INDEX idx_trial_sites_site ON trial_sites(site_id);
CREATE INDEX idx_trial_investigators_trial ON trial_investigators(trial_id);
CREATE INDEX idx_trial_investigators_investigator ON trial_investigators(investigator_id);
CREATE INDEX idx_investigator_sites_investigator ON investigator_sites(investigator_id);
CREATE INDEX idx_investigator_sites_site ON investigator_sites(site_id);

-- ============================================
-- FUNCTIONS
-- ============================================

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to tables
CREATE TRIGGER trials_updated_at
    BEFORE UPDATE ON trials
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER sites_updated_at
    BEFORE UPDATE ON sites
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

CREATE TRIGGER investigators_updated_at
    BEFORE UPDATE ON investigators
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ============================================
-- ROW LEVEL SECURITY (optional, for Supabase)
-- ============================================

-- For now, allow public read access (no auth required for MVP)
ALTER TABLE trials ENABLE ROW LEVEL SECURITY;
ALTER TABLE sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigators ENABLE ROW LEVEL SECURITY;
ALTER TABLE trial_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE trial_investigators ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigator_sites ENABLE ROW LEVEL SECURITY;
ALTER TABLE investigator_metrics ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_metrics ENABLE ROW LEVEL SECURITY;

-- Public read policies
CREATE POLICY "Public read access" ON trials FOR SELECT USING (true);
CREATE POLICY "Public read access" ON sites FOR SELECT USING (true);
CREATE POLICY "Public read access" ON investigators FOR SELECT USING (true);
CREATE POLICY "Public read access" ON trial_sites FOR SELECT USING (true);
CREATE POLICY "Public read access" ON trial_investigators FOR SELECT USING (true);
CREATE POLICY "Public read access" ON investigator_sites FOR SELECT USING (true);
CREATE POLICY "Public read access" ON investigator_metrics FOR SELECT USING (true);
CREATE POLICY "Public read access" ON site_metrics FOR SELECT USING (true);
