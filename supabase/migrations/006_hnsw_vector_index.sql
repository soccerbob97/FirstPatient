-- Migration: Add HNSW index for fast vector similarity search
-- 
-- This index dramatically improves vector search performance:
-- - Without index: O(n) brute force scan (~2-10s for 500K+ vectors)
-- - With HNSW index: O(log n) approximate search (~0.1-0.5s)
--
-- IMPORTANT: Run this AFTER embeddings are complete, as:
-- 1. Index build time increases with more vectors
-- 2. New inserts are slower with index present
--
-- Estimated build time: 10-30 minutes for 500K vectors
-- Memory usage: ~2-4GB during build

-- Enable pgvector extension (should already exist)
CREATE EXTENSION IF NOT EXISTS vector;

-- Create HNSW index on trials.embedding column
-- Parameters:
--   m = 16: Number of connections per layer (higher = more accurate, more memory)
--   ef_construction = 64: Size of dynamic candidate list during build (higher = better quality, slower build)
CREATE INDEX CONCURRENTLY IF NOT EXISTS trials_embedding_hnsw_idx 
ON trials 
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Create index on investigators.embedding if it exists and has data
-- (Uncomment if you're also embedding investigators)
-- CREATE INDEX CONCURRENTLY IF NOT EXISTS investigators_embedding_hnsw_idx 
-- ON investigators 
-- USING hnsw (embedding vector_cosine_ops)
-- WITH (m = 16, ef_construction = 64);

-- Update the search function to use the index efficiently
-- The index is used automatically when using <=> (cosine distance) operator
-- No changes needed to search_trials_by_embedding function

-- Verify index was created
-- Run: SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'trials' AND indexname LIKE '%embedding%';

COMMENT ON INDEX trials_embedding_hnsw_idx IS 'HNSW index for fast approximate nearest neighbor search on trial embeddings. Created for vector similarity search optimization.';
