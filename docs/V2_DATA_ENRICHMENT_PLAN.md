# V2 Data Enrichment Plan

## Overview

This document outlines the plan to enhance search quality by:
1. Integrating drug/intervention data into embeddings
2. Enriching investigator profiles with Semantic Scholar data
3. Adding site classification and metrics
4. Implementing multi-vector search architecture

**Target**: Post-V1 release

---

## Current State (V1)

### Data Sources
- **ClinicalTrials.gov** only

### Tables
| Table | Records | Embedding |
|-------|---------|-----------|
| trials | ~577K | ✅ `brief_title + brief_summary + conditions` |
| investigators | ~738K | ❌ None |
| sites | ~1M | ❌ None |
| interventions | NEW | ❌ None |

### Search Flow
1. Query → embedding
2. Vector search on trials
3. Join to get PI-site pairs
4. Apply metric-based scoring

---

## V2 Enhancements

### Phase 1: Interventions in Embeddings (Priority: HIGH)

**Goal**: Enable drug-aware search ("Find PI for Keytruda trial")

#### Schema (confirm with friend)
```sql
-- Expected interventions table
CREATE TABLE interventions (
    id BIGSERIAL PRIMARY KEY,
    trial_id BIGINT REFERENCES trials(id),
    nct_id VARCHAR(20),
    intervention_type VARCHAR(50),  -- DRUG, BIOLOGICAL, DEVICE, PROCEDURE, etc.
    name VARCHAR(500),
    description TEXT,
    arm_group_label VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_interventions_trial ON interventions(trial_id);
CREATE INDEX idx_interventions_name ON interventions(name);
```

#### Embedding Update
```python
def build_trial_text_for_embedding(trial: dict, interventions: list[str]) -> str:
    parts = []
    if trial.get("brief_title"):
        parts.append(f"Title: {trial['brief_title']}")
    if trial.get("brief_summary"):
        parts.append(f"Summary: {trial['brief_summary'][:500]}")
    if trial.get("conditions"):
        conditions = trial["conditions"] if isinstance(trial["conditions"], list) else [trial["conditions"]]
        parts.append(f"Conditions: {', '.join(conditions)}")
    if interventions:
        parts.append(f"Interventions: {', '.join(interventions)}")
    if trial.get("phase"):
        parts.append(f"Phase: {trial['phase']}")
    return " ".join(parts)
```

#### Migration Script
```python
# scripts/update_embeddings_with_drugs.py
# 1. Fetch trials with interventions
# 2. Rebuild embedding text including drug names
# 3. Batch update embeddings
```

**Estimated effort**: 1-2 days
**Expected impact**: HIGH - enables drug name matching

---

### Phase 2: Semantic Scholar Integration (Priority: HIGH)

**Goal**: Enrich investigator profiles with publication data

#### API Details
- **Endpoint**: `https://api.semanticscholar.org/graph/v1/author/search`
- **Rate limit**: 100 req/5min (free), 100 req/sec (with API key)
- **Fields available**: `name, affiliations, paperCount, citationCount, hIndex, papers`

#### New Investigator Columns
```sql
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS semantic_scholar_id VARCHAR(20);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS h_index INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS paper_count INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS citation_count INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS affiliations_s2 TEXT[];
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS research_areas TEXT[];
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS notable_papers JSONB;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS expertise_embedding vector(1536);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_enriched_at TIMESTAMPTZ;

CREATE INDEX idx_investigators_h_index ON investigators(h_index);
CREATE INDEX idx_investigators_s2_id ON investigators(semantic_scholar_id);
```

#### Matching Strategy
```python
def match_investigator_to_s2(name: str, affiliation: str) -> dict | None:
    """
    Match CT.gov investigator to Semantic Scholar author.
    
    Strategy:
    1. Search by name
    2. Filter by affiliation similarity
    3. Verify with paper topics matching trial conditions
    """
    # Search S2 by name
    response = requests.get(
        "https://api.semanticscholar.org/graph/v1/author/search",
        params={"query": name, "fields": "name,affiliations,paperCount,hIndex"}
    )
    
    candidates = response.json().get("data", [])
    
    # Score candidates by affiliation match
    best_match = None
    best_score = 0
    for candidate in candidates:
        score = fuzzy_match(affiliation, candidate.get("affiliations", []))
        if score > best_score and score > 0.7:
            best_match = candidate
            best_score = score
    
    return best_match
```

#### Expertise Embedding Text
```python
def build_investigator_expertise_text(inv: dict) -> str:
    """Build text for investigator expertise embedding."""
    parts = [f"{inv['full_name']}"]
    
    if inv.get("research_areas"):
        parts.append(f"Research areas: {', '.join(inv['research_areas'])}")
    
    if inv.get("h_index"):
        parts.append(f"h-index: {inv['h_index']}")
    
    if inv.get("notable_papers"):
        titles = [p["title"] for p in inv["notable_papers"][:5]]
        parts.append(f"Notable publications: {'; '.join(titles)}")
    
    if inv.get("affiliations_s2"):
        parts.append(f"Affiliations: {', '.join(inv['affiliations_s2'])}")
    
    return " ".join(parts)
```

**Estimated effort**: 3-5 days
**Expected impact**: HIGH - enables expertise-based PI matching

---

### Phase 3: Site Enrichment (Priority: MEDIUM)

**Goal**: Classify sites and compute therapeutic focus

#### New Site Columns
```sql
ALTER TABLE sites ADD COLUMN IF NOT EXISTS ror_id VARCHAR(20);
ALTER TABLE sites ADD COLUMN IF NOT EXISTS institution_type VARCHAR(50);
  -- Values: 'academic_medical_center', 'community_hospital', 'cro', 
  --         'pharma_site', 'private_practice', 'government', 'other'
ALTER TABLE sites ADD COLUMN IF NOT EXISTS therapeutic_areas TEXT[];
ALTER TABLE sites ADD COLUMN IF NOT EXISTS total_investigators INTEGER DEFAULT 0;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS site_embedding vector(1536);

CREATE INDEX idx_sites_institution_type ON sites(institution_type);
CREATE INDEX idx_sites_therapeutic ON sites USING GIN(therapeutic_areas);
```

#### Therapeutic Areas Computation
```sql
-- Compute from linked trials
UPDATE sites s
SET therapeutic_areas = (
    SELECT ARRAY_AGG(DISTINCT unnest(t.conditions))
    FROM trial_sites ts
    JOIN trials t ON ts.trial_id = t.id
    WHERE ts.site_id = s.id
    LIMIT 20
);
```

#### Site Embedding Text
```python
def build_site_profile_text(site: dict) -> str:
    parts = [site["facility_name"]]
    
    if site.get("city") and site.get("country"):
        parts.append(f"Location: {site['city']}, {site['country']}")
    
    if site.get("institution_type"):
        parts.append(f"Type: {site['institution_type'].replace('_', ' ')}")
    
    if site.get("therapeutic_areas"):
        parts.append(f"Therapeutic focus: {', '.join(site['therapeutic_areas'][:10])}")
    
    return " ".join(parts)
```

**Estimated effort**: 2-3 days
**Expected impact**: MEDIUM - enables site type filtering

---

### Phase 4: Multi-Vector Search (Priority: MEDIUM)

**Goal**: Search across all entity embeddings with weighted combination

#### Updated Recommendation Function
```sql
CREATE OR REPLACE FUNCTION recommend_pi_site_pairs_v2(
    query_embedding vector(1536),
    target_phase varchar DEFAULT NULL,
    target_country varchar DEFAULT NULL,
    target_institution_type varchar DEFAULT NULL,
    min_h_index int DEFAULT NULL,
    similarity_threshold float DEFAULT 0.5,
    max_results int DEFAULT 20
)
RETURNS TABLE (
    investigator_id bigint,
    investigator_name varchar,
    h_index int,
    site_id bigint,
    site_name varchar,
    site_city varchar,
    site_country varchar,
    institution_type varchar,
    trial_similarity float,
    expertise_similarity float,
    site_similarity float,
    combined_score float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    WITH 
    -- Trial matches
    trial_matches AS (
        SELECT t.id, 1 - (t.embedding <=> query_embedding) AS similarity
        FROM trials t
        WHERE t.embedding IS NOT NULL
          AND 1 - (t.embedding <=> query_embedding) > similarity_threshold
          AND (target_phase IS NULL OR t.phase = target_phase)
        ORDER BY t.embedding <=> query_embedding
        LIMIT 200
    ),
    
    -- PI matches (expertise embedding)
    pi_matches AS (
        SELECT i.id, 1 - (i.expertise_embedding <=> query_embedding) AS similarity
        FROM investigators i
        WHERE i.expertise_embedding IS NOT NULL
          AND (min_h_index IS NULL OR i.h_index >= min_h_index)
        ORDER BY i.expertise_embedding <=> query_embedding
        LIMIT 200
    ),
    
    -- Site matches
    site_matches AS (
        SELECT s.id, 1 - (s.site_embedding <=> query_embedding) AS similarity
        FROM sites s
        WHERE s.site_embedding IS NOT NULL
          AND (target_country IS NULL OR s.country ILIKE '%' || target_country || '%')
          AND (target_institution_type IS NULL OR s.institution_type = target_institution_type)
        ORDER BY s.site_embedding <=> query_embedding
        LIMIT 200
    ),
    
    -- Combine via joins
    combined AS (
        SELECT 
            ti.investigator_id,
            i.full_name AS investigator_name,
            i.h_index,
            ts.site_id,
            s.facility_name AS site_name,
            s.city AS site_city,
            s.country AS site_country,
            s.institution_type,
            COALESCE(tm.similarity, 0) AS trial_sim,
            COALESCE(pm.similarity, 0) AS pi_sim,
            COALESCE(sm.similarity, 0) AS site_sim
        FROM trial_matches tm
        JOIN trial_investigators ti ON tm.id = ti.trial_id
        JOIN trial_sites ts ON tm.id = ts.trial_id
        JOIN investigators i ON ti.investigator_id = i.id
        JOIN sites s ON ts.site_id = s.id
        LEFT JOIN pi_matches pm ON i.id = pm.id
        LEFT JOIN site_matches sm ON s.id = sm.id
    )
    
    SELECT 
        c.investigator_id,
        c.investigator_name,
        c.h_index,
        c.site_id,
        c.site_name,
        c.site_city,
        c.site_country,
        c.institution_type,
        c.trial_sim,
        c.pi_sim,
        c.site_sim,
        -- Weighted combination
        (0.50 * c.trial_sim + 0.30 * c.pi_sim + 0.20 * c.site_sim) AS combined_score
    FROM combined c
    ORDER BY combined_score DESC
    LIMIT max_results;
END;
$$;
```

**Estimated effort**: 2-3 days
**Expected impact**: HIGH - holistic matching across all entities

---

## Metrics Usage (NOT in Embeddings)

Metrics should be used for **scoring and filtering**, not embeddings:

### In Scoring Formula
```python
final_score = (
    0.35 * semantic_similarity +      # From embeddings
    0.20 * experience_score +          # total_trials / 20
    0.15 * completion_rate +           # From metrics
    0.15 * h_index_score +             # h_index / 50 (capped)
    0.15 * link_confidence             # Role-based
)
```

### As Filters
```sql
WHERE i.h_index >= :min_h_index
  AND im.completion_rate >= :min_completion_rate
  AND s.institution_type = :institution_type
```

---

## Data Quality Considerations

### Semantic Scholar Matching Challenges
1. **Name ambiguity**: "John Smith" matches many authors
2. **Affiliation changes**: PI may have moved institutions
3. **Missing profiles**: Not all clinical PIs publish academically

### Mitigation
- Require high affiliation match score (>0.7)
- Cross-reference with trial conditions vs paper topics
- Flag low-confidence matches for manual review
- Store `match_confidence` score

---

## Timeline Estimate

| Phase | Effort | Dependencies |
|-------|--------|--------------|
| Phase 1: Interventions | 1-2 days | Interventions table ready |
| Phase 2: Semantic Scholar | 3-5 days | S2 API key |
| Phase 3: Site Enrichment | 2-3 days | None |
| Phase 4: Multi-Vector | 2-3 days | Phases 2-3 complete |
| **Total** | **8-13 days** | |

---

## Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Drug name search recall | 0% | >80% |
| PI expertise match precision | ~40% | >70% |
| User satisfaction (qualitative) | Baseline | +30% |
| Search latency | <500ms | <500ms (maintain) |

---

## Open Questions

1. **Semantic Scholar API key**: Need to obtain for production rate limits
2. **Interventions table schema**: Confirm exact structure
3. **Institution classification**: Manual vs automated (ROR API)?
4. **Embedding model**: Stick with OpenAI or consider domain-specific (PubMedBERT)?
