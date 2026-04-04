-- Add vector embeddings support for semantic search
-- Run this in Supabase SQL Editor after 001_initial_schema.sql

-- ============================================
-- ENABLE PGVECTOR EXTENSION
-- ============================================
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================
-- ADD EMBEDDING COLUMNS TO TRIALS
-- ============================================
-- Embedding of brief_summary + conditions for semantic search
ALTER TABLE trials ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Create index for fast similarity search
CREATE INDEX IF NOT EXISTS idx_trials_embedding 
ON trials USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- ============================================
-- ADD EMBEDDING COLUMNS TO INVESTIGATORS
-- ============================================
-- Derived expertise profile (generated from trial history)
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS expertise_profile TEXT;

-- Embedding of expertise profile
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS embedding vector(1536);

-- Create index for fast similarity search
CREATE INDEX IF NOT EXISTS idx_investigators_embedding 
ON investigators USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- ============================================
-- SIMILARITY SEARCH FUNCTIONS
-- ============================================

-- Function to search trials by semantic similarity
CREATE OR REPLACE FUNCTION search_trials_by_embedding(
    query_embedding vector(1536),
    similarity_threshold float DEFAULT 0.7,
    max_results int DEFAULT 50
)
RETURNS TABLE (
    id bigint,
    nct_id varchar,
    brief_title text,
    conditions text[],
    phase varchar,
    overall_status varchar,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        t.id,
        t.nct_id,
        t.brief_title,
        t.conditions,
        t.phase,
        t.overall_status,
        1 - (t.embedding <=> query_embedding) AS similarity
    FROM trials t
    WHERE t.embedding IS NOT NULL
      AND 1 - (t.embedding <=> query_embedding) > similarity_threshold
    ORDER BY t.embedding <=> query_embedding
    LIMIT max_results;
END;
$$;

-- Function to search investigators by semantic similarity
CREATE OR REPLACE FUNCTION search_investigators_by_embedding(
    query_embedding vector(1536),
    similarity_threshold float DEFAULT 0.7,
    max_results int DEFAULT 50
)
RETURNS TABLE (
    id bigint,
    full_name varchar,
    affiliation text,
    expertise_profile text,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        i.id,
        i.full_name,
        i.affiliation,
        i.expertise_profile,
        1 - (i.embedding <=> query_embedding) AS similarity
    FROM investigators i
    WHERE i.embedding IS NOT NULL
      AND 1 - (i.embedding <=> query_embedding) > similarity_threshold
    ORDER BY i.embedding <=> query_embedding
    LIMIT max_results;
END;
$$;

-- ============================================
-- RECOMMENDATION FUNCTION (HYBRID SEARCH)
-- ============================================

-- Main recommendation function combining vector search + heuristics
CREATE OR REPLACE FUNCTION recommend_pi_site_pairs(
    query_embedding vector(1536),
    target_phase varchar DEFAULT NULL,
    target_country varchar DEFAULT NULL,
    similarity_threshold float DEFAULT 0.5,
    max_results int DEFAULT 20
)
RETURNS TABLE (
    investigator_id bigint,
    investigator_name varchar,
    site_id bigint,
    site_name varchar,
    site_city varchar,
    site_country varchar,
    link_type varchar,
    avg_trial_similarity float,
    total_trials bigint,
    completion_rate numeric,
    final_score float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH 
    -- Step 1: Find semantically similar trials
    relevant_trials AS (
        SELECT 
            t.id AS trial_id,
            1 - (t.embedding <=> query_embedding) AS similarity
        FROM trials t
        WHERE t.embedding IS NOT NULL
          AND 1 - (t.embedding <=> query_embedding) > similarity_threshold
          AND (target_phase IS NULL OR t.phase = target_phase)
        ORDER BY t.embedding <=> query_embedding
        LIMIT 200
    ),
    
    -- Step 2: Find PI-site pairs from these trials
    pi_site_candidates AS (
        SELECT 
            inv_s.investigator_id,
            inv_s.site_id,
            inv_s.link_type,
            AVG(rt.similarity) AS avg_similarity,
            COUNT(DISTINCT rt.trial_id) AS trial_count
        FROM investigator_sites inv_s
        JOIN trial_sites ts ON inv_s.site_id = ts.site_id
        JOIN relevant_trials rt ON ts.trial_id = rt.trial_id
        GROUP BY inv_s.investigator_id, inv_s.site_id, inv_s.link_type
    ),
    
    -- Step 3: Enrich with investigator and site details + metrics
    enriched_candidates AS (
        SELECT 
            psc.investigator_id,
            i.full_name AS investigator_name,
            psc.site_id,
            s.facility_name AS site_name,
            s.city AS site_city,
            s.country AS site_country,
            psc.link_type,
            psc.avg_similarity,
            psc.trial_count,
            COALESCE(im.total_trials, 0) AS total_trials,
            COALESCE(im.completion_rate, 0) AS completion_rate,
            -- Link type bonus: site_contact > affiliation_match > oversight
            CASE psc.link_type
                WHEN 'site_contact' THEN 0.15
                WHEN 'affiliation_match' THEN 0.10
                ELSE 0.0
            END AS link_bonus
        FROM pi_site_candidates psc
        JOIN investigators i ON psc.investigator_id = i.id
        JOIN sites s ON psc.site_id = s.id
        LEFT JOIN investigator_metrics im ON i.id = im.investigator_id
        WHERE target_country IS NULL OR s.country ILIKE '%' || target_country || '%'
    ),
    
    -- Step 4: Compute final score
    scored_candidates AS (
        SELECT 
            ec.*,
            (
                0.40 * ec.avg_similarity +                           -- Semantic relevance
                0.25 * LEAST(ec.total_trials::float / 20.0, 1.0) +   -- Experience (capped at 20 trials)
                0.20 * ec.completion_rate +                          -- Track record
                0.15 * ec.link_bonus                                 -- Link confidence
            ) AS final_score
        FROM enriched_candidates ec
    )
    
    SELECT 
        sc.investigator_id,
        sc.investigator_name,
        sc.site_id,
        sc.site_name,
        sc.site_city,
        sc.site_country,
        sc.link_type,
        sc.avg_similarity,
        sc.total_trials,
        sc.completion_rate,
        sc.final_score
    FROM scored_candidates sc
    ORDER BY sc.final_score DESC
    LIMIT max_results;
END;
$$;
