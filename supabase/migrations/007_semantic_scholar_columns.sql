-- Migration: Add Semantic Scholar enrichment columns to investigators
-- 
-- This adds columns to store publication data from Semantic Scholar API:
-- - h_index, paper_count, citation_count for ranking
-- - research_areas for expertise matching
-- - notable_papers for display and embeddings
--
-- Safe to run while HNSW index is building (different table)

-- Add Semantic Scholar enrichment columns
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS semantic_scholar_id VARCHAR(20);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS h_index INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS paper_count INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS citation_count INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS affiliations_s2 TEXT[];
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS research_areas TEXT[];
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS notable_papers JSONB;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_match_confidence DECIMAL(3,2);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_enriched_at TIMESTAMPTZ;

-- Indexes for filtering and sorting by academic metrics
CREATE INDEX IF NOT EXISTS idx_investigators_h_index ON investigators(h_index) WHERE h_index IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_investigators_s2_id ON investigators(semantic_scholar_id) WHERE semantic_scholar_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_investigators_paper_count ON investigators(paper_count) WHERE paper_count IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_investigators_research_areas ON investigators USING GIN(research_areas) WHERE research_areas IS NOT NULL;

-- Add column for expertise embedding (for V2 multi-vector search)
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS expertise_embedding vector(1536);

-- Index for expertise embedding search (uncomment when ready to use)
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS investigators_expertise_hnsw_idx 
-- ON investigators 
-- USING hnsw (expertise_embedding vector_cosine_ops)
-- WITH (m = 16, ef_construction = 64);

COMMENT ON COLUMN investigators.semantic_scholar_id IS 'Semantic Scholar author ID';
COMMENT ON COLUMN investigators.h_index IS 'h-index from Semantic Scholar';
COMMENT ON COLUMN investigators.paper_count IS 'Total publications in Semantic Scholar';
COMMENT ON COLUMN investigators.citation_count IS 'Total citations in Semantic Scholar';
COMMENT ON COLUMN investigators.affiliations_s2 IS 'Affiliations from Semantic Scholar profile';
COMMENT ON COLUMN investigators.research_areas IS 'Research areas extracted from publications';
COMMENT ON COLUMN investigators.notable_papers IS 'Top 5 papers by citation count [{title, citationCount}]';
COMMENT ON COLUMN investigators.s2_match_confidence IS 'Confidence score of S2 author match (0-1)';
COMMENT ON COLUMN investigators.s2_enriched_at IS 'Timestamp when S2 data was fetched';
COMMENT ON COLUMN investigators.expertise_embedding IS 'Embedding of expertise profile for semantic search';
