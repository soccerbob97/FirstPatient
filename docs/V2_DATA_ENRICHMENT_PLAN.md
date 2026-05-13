# V2 Data Enrichment Plan

## Overview

This document outlines the V2 plan to enhance search quality through:
1. **Data enrichment first** - Add all new fields to tables before any embedding work
2. **Single-pass embedding** - Generate embeddings once after all data is enriched
3. **Hybrid search** - Combine semantic search with metadata filtering/ranking

**Key Principle**: Embeddings are expensive (time + cost). Enrich ALL data first, then embed once.

---

## Rollout Strategy: Subset Testing → Production

We will validate the V2 approach on a **subset of trials** before applying to the full dataset.

### Why Subset Testing?
- Validate ORCID + S2 matching quality before full enrichment
- Test Voyage-3.5-lite embeddings vs current OpenAI embeddings
- Ensure search quality improves before production rollout
- **No risk to production app** - uses separate test tables

### Subset Definition
**Conditions**: Diabetes, Breast Cancer, Obesity

| Condition | Est. Trials | Est. Investigators |
|-----------|-------------|-------------------|
| Diabetes | ~15K | ~8K |
| Breast Cancer | ~12K | ~6K |
| Obesity | ~5K | ~3K |
| **Total (deduplicated)** | **~30K** | **~15K** |

### Filter Query
```sql
SELECT t.id, t.nct_id, t.brief_title, t.conditions
FROM trials t
WHERE 
  -- Diabetes
  t.brief_title ILIKE ANY(ARRAY['%diabetes%', '%diabetic%', '%t1d%', '%t2d%', '%insulin%', '%glycemic%', '%hba1c%'])
  OR t.conditions::text ILIKE ANY(ARRAY['%diabetes%', '%diabetic%'])
  -- Breast Cancer
  OR t.brief_title ILIKE ANY(ARRAY['%breast cancer%', '%breast neoplasm%', '%breast tumor%', '%mammary%', '%mastectomy%'])
  OR t.conditions::text ILIKE ANY(ARRAY['%breast cancer%', '%breast neoplasm%'])
  -- Obesity
  OR t.brief_title ILIKE ANY(ARRAY['%obesity%', '%obese%', '%overweight%', '%weight loss%', '%bariatric%', '%bmi%'])
  OR t.conditions::text ILIKE ANY(ARRAY['%obesity%', '%obese%']);
```

### Isolation Strategy

| Component | Production | Test (Isolated) |
|-----------|------------|-----------------|
| `trials` table | Unchanged | Read-only (same table) |
| `investigators` table | + new columns (additive) | Enrich subset only |
| `sites` table | + new columns (additive) | Read-only |
| `trials_embeddings` | Unchanged (1536d, OpenAI) | — |
| `trials_embeddings_v2_test` | — | New table (1024d, Voyage) |
| `search_trials()` | Unchanged | — |
| `search_trials_v2_test()` | — | New function |

**Production app continues using original tables/functions. Test scripts use `_v2_test` tables.**

### Rollout Phases

```
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE A: SUBSET TESTING (No production impact)                      │
├─────────────────────────────────────────────────────────────────────┤
│ A1. Add columns to investigators/sites tables (additive, safe)      │
│ A2. Create trials_embeddings_v2_test table (1024 dimensions)        │
│ A3. Create search_trials_v2_test() function                         │
│ A4. Filter subset trials (diabetes, breast cancer, obesity)         │
│ A5. Run ORCID + S2 enrichment on subset investigators (~15K)        │
│ A6. Compute derived fields for subset                               │
│ A7. Generate Voyage-3.5-lite embeddings for subset (~30K trials)    │
│ A8. Build HNSW index on test table                                  │
│ A9. Run test queries locally, validate results                      │
│ A10. Compare search quality: V1 vs V2                               │
└─────────────────────────────────────────────────────────────────────┘
                              ↓
                    Validation successful?
                              ↓
┌─────────────────────────────────────────────────────────────────────┐
│ PHASE B: PRODUCTION ROLLOUT (After validation)                      │
├─────────────────────────────────────────────────────────────────────┤
│ B1. Run ORCID + S2 enrichment on ALL investigators (~738K)          │
│ B2. Compute derived fields for all records                          │
│ B3. Generate Voyage-3.5-lite embeddings for ALL trials (~577K)      │
│ B4. Build production HNSW index                                     │
│ B5. Rename test tables → production (or update app to use V2)       │
│ B6. Deploy app changes                                              │
│ B7. Monitor and validate                                            │
└─────────────────────────────────────────────────────────────────────┘
```

### Test Scripts (Local Only)

All testing done via local scripts - **no app code changes until Phase B**:

```
scripts/v2_test/
├── 01_setup_test_tables.py      # Create trials_embeddings_v2_test, search function
├── 02_get_subset_trials.py      # Filter diabetes/breast cancer/obesity trials
├── 03_enrich_subset_pis.py      # Run ORCID+S2 on subset investigators
├── 04_compute_derived_fields.py # therapeutic_areas, total_trials, etc.
├── 05_generate_embeddings.py    # Voyage-3.5-lite embeddings for subset
├── 06_test_search.py            # Test queries, compare V1 vs V2
└── README.md                    # Instructions
```

---

## Current State (V1)

### Database Size
| Component | Size |
|-----------|------|
| Trial embeddings | ~6 GB |
| HNSW index | ~3 GB |
| **Total embedding storage** | **~9 GB** |

### Tables
| Table | Records | Embedding | Key Fields |
|-------|---------|-----------|------------|
| trials | ~577K | ✅ 1536d | brief_title, brief_summary, conditions |
| investigators | ~738K | ❌ None | full_name, affiliation, role |
| sites | ~1M | ❌ None | facility_name, city, country |
| interventions | ~1.2M | ❌ None | name, type, description |

### Current Search Flow
```
Query → embed → vector search (trials) → join PIs/sites → score by metrics
```

---

## V2 Architecture Decision

### The Problem
Creating embeddings for every table would result in:
- Investigators: ~738K × 6KB = ~4.4 GB embeddings + ~2.2 GB index
- Sites: ~1M × 6KB = ~6 GB embeddings + ~3 GB index
- **Total additional**: ~15 GB (on top of existing 9 GB)

### The Solution: Enriched Trial Embeddings + Metadata Filtering

**One embedding per trial** that includes PI, site, and intervention context.
**Metadata columns** on investigators/sites for filtering, ranking, display, and tool calling.

```
Query: "Find experienced oncology PI in Germany"

1. Semantic search: "oncology" matches trial conditions in embedding
2. Join: Get linked PIs and sites
3. Filter: WHERE sites.country = 'Germany' (structured metadata only)
4. Rank: ORDER BY investigators.h_index DESC, investigators.total_trials DESC
5. Display: Show PI's therapeutic_areas, affiliations in results
```

**Key insight**: Topic matching (e.g., "oncology") is handled by semantic search on trial conditions. 
The `therapeutic_areas` field on PIs/sites is for **display and tool calling only**, not filtering.

---

## Phase 1: Data Enrichment (Before Any Embedding)

### 1.1 Interventions Table (Already Exists - No Changes Needed)

Your friend has already created this table. No modifications required.

---

### 1.2 Investigators Table

**New columns**:
```sql
-- ============================================
-- FROM ORCID + SEMANTIC SCHOLAR API (scraped)
-- ============================================
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS orcid_id VARCHAR(20);          -- ORCID identifier (e.g., 0000-0002-1825-0097)
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS semantic_scholar_id VARCHAR(20);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS h_index INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS paper_count INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS citation_count INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS affiliations_s2 TEXT[];       -- For tool calling
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS notable_papers JSONB;          -- For tool calling [{title, year, citations}]
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS research_areas TEXT[];         -- For display + tool calling
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_match_confidence DECIMAL(3,2);  -- Match quality (0-1)
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_match_source VARCHAR(20);   -- 'orcid', 's2_affiliation', 's2_topics'
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_enriched_at TIMESTAMPTZ;    -- When S2 data was fetched

-- ============================================
-- DERIVED FROM TRIAL HISTORY (computed locally)
-- ============================================
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS therapeutic_areas TEXT[];  -- For display + tool calling (NOT filtering)
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS total_trials INTEGER DEFAULT 0;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS years_active INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS primary_role VARCHAR(50);  -- Most common role

-- ============================================
-- INDEXES (for filtering/ranking)
-- ============================================
CREATE INDEX IF NOT EXISTS idx_investigators_h_index ON investigators(h_index) WHERE h_index IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_investigators_total_trials ON investigators(total_trials);
```

**Field purposes**:
| Field | Source | Purpose |
|-------|--------|---------|
| `orcid_id` | ORCID API | **High-confidence identifier** for S2 lookup |
| `semantic_scholar_id` | S2 API | Link to S2 profile |
| `h_index` | S2 API | **Filtering + Scoring** |
| `paper_count` | S2 API | Display + Tool calling |
| `citation_count` | S2 API | Display + Tool calling |
| `affiliations_s2` | S2 API | **Tool calling** ("Where does Dr. X work?") |
| `notable_papers` | S2 API | **Tool calling** ("What has Dr. X published?") |
| `research_areas` | S2 API | Display + Tool calling |
| `s2_match_confidence` | Computed | Filter low-confidence matches |
| `s2_match_source` | Computed | How match was made: 'orcid', 's2_affiliation', 's2_topics' |
| `s2_enriched_at` | Timestamp | Track enrichment status, re-enrich stale data |
| `therapeutic_areas` | Derived | **Display + Tool calling** (NOT for filtering) |
| `total_trials` | Derived | **Scoring** |
| `years_active` | Derived | Display |
| `primary_role` | Derived | Scoring |

**Why `therapeutic_areas` is NOT used for filtering**:
- Semantic search on trial conditions already handles topic matching
- A PI with 50+ trials could have 100+ therapeutic areas - inefficient to search
- Redundant with trial-level filtering

---

### 1.3 Sites Table

**New columns**:
```sql
-- ============================================
-- CLASSIFICATION (derived from facility_name)
-- ============================================
ALTER TABLE sites ADD COLUMN IF NOT EXISTS institution_type VARCHAR(50);
  -- Values: 'academic_medical_center', 'community_hospital', 'cro', 
  --         'pharma_site', 'private_practice', 'government', 'other'

-- ============================================
-- DERIVED FROM TRIAL HISTORY (computed locally)
-- ============================================
ALTER TABLE sites ADD COLUMN IF NOT EXISTS therapeutic_areas TEXT[];  -- For display + tool calling (NOT filtering)
ALTER TABLE sites ADD COLUMN IF NOT EXISTS total_trials INTEGER DEFAULT 0;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS total_investigators INTEGER DEFAULT 0;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS active_since INTEGER;  -- Earliest trial year

-- ============================================
-- INDEXES (for filtering)
-- ============================================
CREATE INDEX IF NOT EXISTS idx_sites_institution_type ON sites(institution_type) WHERE institution_type IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_sites_country ON sites(country);
```

**Field purposes**:
| Field | Source | Purpose |
|-------|--------|---------|
| `institution_type` | Keyword classification | **Filtering** ("Find academic medical centers") |
| `therapeutic_areas` | Derived from trials | **Display + Tool calling** (NOT filtering) |
| `total_trials` | Computed | Display |
| `total_investigators` | Computed | Display |
| `active_since` | Computed | Display |

**Data sources**:
- `institution_type` → Regex classification from `facility_name`
- `therapeutic_areas` → Aggregated from linked trials' conditions
- `total_trials`, `total_investigators` → Computed from junction tables

---

### 1.4 Trials Table

**New columns to cache for embedding**:
```sql
-- ============================================
-- CACHED FOR EMBEDDING GENERATION
-- ============================================
ALTER TABLE trials ADD COLUMN IF NOT EXISTS intervention_names TEXT[];
ALTER TABLE trials ADD COLUMN IF NOT EXISTS lead_pi_name VARCHAR(255);
ALTER TABLE trials ADD COLUMN IF NOT EXISTS lead_site_names TEXT[];  -- Top 2-3 sites
ALTER TABLE trials ADD COLUMN IF NOT EXISTS embedding_text TEXT;     -- Pre-computed full text
```

**Why cache these?**
- Avoids expensive joins during embedding generation
- `lead_site_names` is TEXT[] to include top 2-3 sites (not just one)

---

## Phase 2: ORCID + Semantic Scholar Enrichment

**Goal**: Add h-index, publication data, affiliations, and notable papers for **70-85% of real PIs**.

**Script**: `scripts/enrich_investigators_s2.py` (to be updated)

**Documentation**: See `docs/SEMANTIC_SCHOLAR_SCRAPING.md` for full details.

### 2.1 Multi-Source Matching Strategy

To achieve higher match rates, we use a **two-step approach**:

```
For each investigator (name, affiliation):

Step 1: Try ORCID first (highest confidence)
   a. Parse name into given-names + family-name
   b. Search ORCID API: family-name:{last} AND given-names:{first} AND affiliation-org-name:"{affiliation}"
   c. If ORCID found (confidence > 0.8):
      → Use ORCID to lookup S2 profile directly: GET /author/ORCID:{orcid_id}
      → Store orcid_id, set s2_match_source = 'orcid'
      → High confidence match (90%+)

Step 2: Fall back to S2 name search (if no ORCID)
   a. Search S2 API by name: GET /author/search?query={name}
   b. Get candidates with affiliations
   c. Fuzzy match affiliation to CT.gov affiliation
   d. If match confidence > 0.7:
      → Store S2 data, set s2_match_source = 's2_affiliation'
      → Medium confidence match
```

### 2.2 Expected Match Rates

| Strategy | Match Rate | Confidence |
|----------|------------|------------|
| ORCID → S2 lookup | 25-35% | **High (90%+)** |
| S2 name + affiliation | 35-45% | Medium (70-85%) |
| S2 with topic validation | +5-10% | Medium |
| **Combined Total** | **70-85%** | Mixed |

### 2.3 API Details

**ORCID API** (free, requires registration):
| Endpoint | Purpose | Auth |
|----------|---------|------|
| `GET /v3.0/search/?q=...` | Search by name + affiliation | Bearer token |
| `GET /v3.0/{orcid}/record` | Get full ORCID profile | Bearer token |

**Semantic Scholar API**:
| Endpoint | Purpose | Rate Limit |
|----------|---------|------------|
| `GET /author/ORCID:{id}` | Lookup by ORCID (preferred) | 100 req/sec |
| `GET /author/search` | Find author by name | 100 req/sec |
| `GET /author/{id}` | Get full author details | 100 req/sec |
| `POST /author/batch` | Batch lookup (up to 1000) | 100 req/sec |

**S2 Fields to request**:
```
name,affiliations,paperCount,citationCount,hIndex,papers.title,papers.year,papers.citationCount
```

### 2.4 Running the Script

```bash
# Dry run (no database writes)
PYTHONPATH=. python scripts/enrich_investigators_s2.py --dry-run --limit 100

# Full run with ORCID + S2 matching
PYTHONPATH=. python scripts/enrich_investigators_s2.py --limit 10000 --use-orcid

# Resume from checkpoint
PYTHONPATH=. python scripts/enrich_investigators_s2.py --resume
```

**Time estimate**: ~45-60 min for 10K PIs (ORCID adds ~15 min overhead)

---

## Phase 3: Compute Derived Fields

Run these **after** Phase 2 (S2 enrichment) is complete:

### 3.1 Investigator Derived Fields
```sql
-- Therapeutic areas + total trials
UPDATE investigators i
SET therapeutic_areas = subq.areas,
    total_trials = subq.trial_count
FROM (
    SELECT 
        ti.investigator_id,
        ARRAY_AGG(DISTINCT unnest_cond) AS areas,
        COUNT(DISTINCT ti.trial_id) AS trial_count
    FROM trial_investigators ti
    JOIN trials t ON ti.trial_id = t.id
    CROSS JOIN LATERAL unnest(t.conditions) AS unnest_cond
    GROUP BY ti.investigator_id
) subq
WHERE i.id = subq.investigator_id;

-- Years active
UPDATE investigators i
SET years_active = subq.years
FROM (
    SELECT 
        ti.investigator_id,
        EXTRACT(YEAR FROM MAX(t.start_date)) - EXTRACT(YEAR FROM MIN(t.start_date)) AS years
    FROM trial_investigators ti
    JOIN trials t ON ti.trial_id = t.id
    WHERE t.start_date IS NOT NULL
    GROUP BY ti.investigator_id
) subq
WHERE i.id = subq.investigator_id;

-- Primary role (most common)
UPDATE investigators i
SET primary_role = subq.role
FROM (
    SELECT DISTINCT ON (investigator_id)
        investigator_id,
        role,
        COUNT(*) as cnt
    FROM trial_investigators
    GROUP BY investigator_id, role
    ORDER BY investigator_id, cnt DESC
) subq
WHERE i.id = subq.investigator_id;
```

### 3.2 Site Derived Fields
```sql
-- Therapeutic areas + counts
UPDATE sites s
SET therapeutic_areas = subq.areas,
    total_trials = subq.trial_count,
    total_investigators = subq.inv_count
FROM (
    SELECT 
        ts.site_id,
        ARRAY_AGG(DISTINCT unnest_cond) AS areas,
        COUNT(DISTINCT ts.trial_id) AS trial_count,
        COUNT(DISTINCT ti.investigator_id) AS inv_count
    FROM trial_sites ts
    JOIN trials t ON ts.trial_id = t.id
    LEFT JOIN trial_investigators ti ON ti.trial_id = t.id
    CROSS JOIN LATERAL unnest(t.conditions) AS unnest_cond
    GROUP BY ts.site_id
) subq
WHERE s.id = subq.site_id;

-- Active since (earliest trial year)
UPDATE sites s
SET active_since = subq.earliest_year
FROM (
    SELECT 
        ts.site_id,
        EXTRACT(YEAR FROM MIN(t.start_date))::INTEGER AS earliest_year
    FROM trial_sites ts
    JOIN trials t ON ts.trial_id = t.id
    WHERE t.start_date IS NOT NULL
    GROUP BY ts.site_id
) subq
WHERE s.id = subq.site_id;
```

### 3.3 Site Institution Type Classification
```sql
UPDATE sites
SET institution_type = CASE
    WHEN facility_name ~* '(university|medical school|academic|teaching hospital|school of medicine)' THEN 'academic_medical_center'
    WHEN facility_name ~* '(community|regional|general hospital|medical center)' THEN 'community_hospital'
    WHEN facility_name ~* '(cro|contract research|clinical research org|research institute)' THEN 'cro'
    WHEN facility_name ~* '(pharma|pharmaceutical|inc\.|llc|ltd|corp)' THEN 'pharma_site'
    WHEN facility_name ~* '(private|clinic|practice|associates|medical group)' THEN 'private_practice'
    WHEN facility_name ~* '(va |veterans|nih|cdc|government|federal|national institute)' THEN 'government'
    ELSE 'other'
END
WHERE institution_type IS NULL;
```

### 3.4 Cache Trial Fields for Embedding
```sql
-- Cache intervention names
UPDATE trials t
SET intervention_names = subq.names
FROM (
    SELECT trial_id, ARRAY_AGG(DISTINCT name) AS names
    FROM interventions
    WHERE name IS NOT NULL
    GROUP BY trial_id
) subq
WHERE t.id = subq.trial_id;

-- Cache lead PI name (first PI found)
UPDATE trials t
SET lead_pi_name = subq.pi_name
FROM (
    SELECT DISTINCT ON (trial_id)
        ti.trial_id,
        i.full_name AS pi_name
    FROM trial_investigators ti
    JOIN investigators i ON ti.investigator_id = i.id
    WHERE ti.role IN ('PRINCIPAL_INVESTIGATOR', 'STUDY_DIRECTOR')
    ORDER BY trial_id, 
        CASE ti.role WHEN 'PRINCIPAL_INVESTIGATOR' THEN 1 ELSE 2 END
) subq
WHERE t.id = subq.trial_id;

-- Cache lead site names (top 3 sites)
UPDATE trials t
SET lead_site_names = subq.site_names
FROM (
    SELECT 
        ts.trial_id,
        ARRAY_AGG(s.facility_name ORDER BY s.id) AS site_names
    FROM (
        SELECT trial_id, site_id,
            ROW_NUMBER() OVER (PARTITION BY trial_id ORDER BY site_id) AS rn
        FROM trial_sites
    ) ts
    JOIN sites s ON ts.site_id = s.id
    WHERE ts.rn <= 3
    GROUP BY ts.trial_id
) subq
WHERE t.id = subq.trial_id;
```

---

## Phase 4: Generate Embeddings (Single Pass)

### 4.1 Build Embedding Text

**IMPORTANT**: Do this AFTER all enrichment is complete.

```python
def build_trial_embedding_text(trial: dict) -> str:
    """
    Build comprehensive text for trial embedding.
    Includes intervention, PI, and site context.
    """
    parts = []
    
    # Core trial info
    if trial.get("brief_title"):
        parts.append(f"Title: {trial['brief_title']}")
    
    if trial.get("brief_summary"):
        # Truncate to avoid token limits
        summary = trial["brief_summary"][:800]
        parts.append(f"Summary: {summary}")
    
    if trial.get("conditions"):
        conditions = trial["conditions"] if isinstance(trial["conditions"], list) else [trial["conditions"]]
        parts.append(f"Conditions: {', '.join(conditions[:10])}")
    
    if trial.get("phase"):
        parts.append(f"Phase: {trial['phase']}")
    
    # Intervention info (drug names, types)
    if trial.get("intervention_names"):
        parts.append(f"Interventions: {', '.join(trial['intervention_names'][:5])}")
    
    # Lead PI (if available)
    if trial.get("lead_pi_name"):
        parts.append(f"Lead Investigator: {trial['lead_pi_name']}")
    
    # Lead sites (top 2-3)
    if trial.get("lead_site_names"):
        sites = trial["lead_site_names"][:3]
        parts.append(f"Sites: {', '.join(sites)}")
    
    return " ".join(parts)
```

### 4.2 Pre-compute Embedding Text
```sql
-- Build and cache embedding_text for all trials
UPDATE trials t
SET embedding_text = CONCAT_WS(' ',
    'Title: ' || COALESCE(brief_title, ''),
    'Summary: ' || LEFT(COALESCE(brief_summary, ''), 800),
    'Conditions: ' || COALESCE(ARRAY_TO_STRING(conditions, ', '), ''),
    'Phase: ' || COALESCE(phase, ''),
    CASE WHEN intervention_names IS NOT NULL 
         THEN 'Interventions: ' || ARRAY_TO_STRING(intervention_names, ', ')
         ELSE NULL END,
    CASE WHEN lead_pi_name IS NOT NULL 
         THEN 'Lead Investigator: ' || lead_pi_name
         ELSE NULL END,
    CASE WHEN lead_site_names IS NOT NULL 
         THEN 'Sites: ' || ARRAY_TO_STRING(lead_site_names, ', ')
         ELSE NULL END
)
WHERE embedding_text IS NULL;
```

### 4.3 Embedding Model Choice

| Model | Dimensions | Cost | Quality |
|-------|------------|------|---------|
| OpenAI text-embedding-3-small | 1536 | $0.02/1M tokens | Baseline |
| **Voyage-3.5-lite** | 1024 | $0.02/1M tokens | +6.34% better |

**Recommendation**: Use **Voyage-3.5-lite with 1024 dimensions**
- Same cost as OpenAI
- Better quality
- 33% smaller vectors = less storage, faster search

### 4.4 Embedding Generation Script

```bash
# Run AFTER all data enrichment is complete
# Uses pre-computed embedding_text column
PYTHONPATH=. python scripts/generate_embeddings_v2.py \
    --model voyage-3.5-lite \
    --dimensions 1024 \
    --batch-size 100
```

---

## Phase 5: Search Implementation

### 5.1 Hybrid Search Function

```python
def search_v2(
    query: str,
    phase: str = None,
    country: str = None,
    institution_type: str = None,
    min_h_index: int = None,
    min_trials: int = None,
    max_results: int = 10
) -> list[dict]:
    """
    Hybrid search: semantic + metadata filtering + ranking.
    """
    # Step 1: Embed query
    query_embedding = embed(query)
    
    # Step 2: Vector search on trials
    trials = vector_search(
        query_embedding,
        table="trial_embeddings_full",
        limit=max_results * 10,
        threshold=0.5
    )
    
    # Step 3: Get linked PIs and sites
    trial_ids = [t["id"] for t in trials]
    pi_site_pairs = get_pi_site_pairs(trial_ids)
    
    # Step 4: Apply metadata filters
    if country:
        pi_site_pairs = [p for p in pi_site_pairs if p["site_country"] == country]
    if institution_type:
        pi_site_pairs = [p for p in pi_site_pairs if p["institution_type"] == institution_type]
    if min_h_index:
        pi_site_pairs = [p for p in pi_site_pairs if (p.get("h_index") or 0) >= min_h_index]
    if min_trials:
        pi_site_pairs = [p for p in pi_site_pairs if (p.get("total_trials") or 0) >= min_trials]
    
    # Step 5: Score and rank
    for pair in pi_site_pairs:
        pair["score"] = calculate_score(
            similarity=pair["trial_similarity"],
            h_index=pair.get("h_index"),
            total_trials=pair.get("total_trials"),
            role=pair.get("role")
        )
    
    # Step 6: Sort and return
    pi_site_pairs.sort(key=lambda x: x["score"], reverse=True)
    return pi_site_pairs[:max_results]
```

### 5.2 Scoring Formula

```python
def calculate_score(similarity: float, h_index: int, total_trials: int, role: str) -> float:
    """
    Combine semantic similarity with metadata for final ranking.
    """
    # Semantic similarity (0-1)
    sim_score = similarity
    
    # Experience score (log scale, 0-1)
    exp_score = min(0.5 + 0.5 * log10(max(total_trials, 1) + 1) / log10(51), 1.0)
    
    # Academic score (0-1)
    h_score = min((h_index or 0) / 50, 1.0)
    
    # Role confidence (0-1)
    role_scores = {
        "PRINCIPAL_INVESTIGATOR": 1.0,
        "STUDY_DIRECTOR": 0.9,
        "SUB_INVESTIGATOR": 0.7,
        "CONTACT": 0.5,
    }
    role_score = role_scores.get(role, 0.4)
    
    # Weighted combination
    return (
        0.50 * sim_score +      # Semantic match is primary
        0.20 * exp_score +      # Experience matters
        0.15 * h_score +        # Academic reputation
        0.15 * role_score       # Role confidence
    )
```

---

## Implementation Order

| Step | Phase | Task | Dependencies | Effort |
|------|-------|------|--------------|--------|
| 1 | 1 | Add columns to investigators table | None | 30 min |
| 2 | 1 | Add columns to sites table | None | 30 min |
| 3 | 1 | Add columns to trials table | None | 15 min |
| 4 | 2 | **Run Semantic Scholar enrichment** | Step 1 | 1-2 hours |
| 5 | 3 | Compute investigator derived fields | Step 4 | 1 hour |
| 6 | 3 | Compute site derived fields + institution_type | Step 2 | 1 hour |
| 7 | 3 | Cache intervention_names, lead_pi, lead_sites on trials | Step 3 | 30 min |
| 8 | 4 | Build embedding_text for all trials | Steps 5-7 | 30 min |
| 9 | 4 | Generate embeddings (Voyage-3.5-lite, 1024d) | Step 8 | 2-4 hours |
| 10 | 4 | Rebuild HNSW index | Step 9 | 2-4 hours |
| 11 | 5 | Update search function | Step 10 | 2 hours |
| **Total** | | | | **~10-14 hours** |

**Key**: S2 enrichment (Step 4) happens BEFORE derived fields so we have h_index data available.

---

## Storage Estimate (V2)

| Component | V1 Size | V2 Size | Change |
|-----------|---------|---------|--------|
| Trial embeddings | 6 GB (1536d) | 4 GB (1024d) | -33% |
| HNSW index | 3 GB | 2 GB | -33% |
| New metadata columns | - | ~500 MB | +500 MB |
| **Total** | **9 GB** | **~6.5 GB** | **-28%** |

Using Voyage-3.5-lite with 1024 dimensions actually **reduces** storage while improving quality.

---

## Supported Queries After V2

| Query Type | How It Works |
|------------|--------------|
| "Find PI for Keytruda trial" | Drug name in embedding → semantic match |
| "Oncology trials in Germany" | Conditions in embedding → semantic match, then country filter |
| "Experienced oncology PI" | Semantic match on conditions + rank by h_index/total_trials |
| "Academic medical centers in Germany" | Metadata filter: institution_type + country |
| "Phase 2 diabetes trials" | Phase filter + semantic match on "diabetes" |
| "Tell me about Dr. Smith" | **Tool calling** → fetch affiliations_s2, notable_papers, research_areas |
| "What has Dr. Smith published?" | **Tool calling** → fetch notable_papers JSONB |

---

## Tool Calling Support

The following fields are available for tool calling (answering user questions about PIs):

| Field | Example Question |
|-------|------------------|
| `affiliations_s2` | "Where does Dr. Smith work?" |
| `notable_papers` | "What has Dr. Smith published?" |
| `research_areas` | "What does Dr. Smith specialize in?" |
| `therapeutic_areas` | "What conditions has Dr. Smith worked on?" |
| `h_index` | "How experienced is Dr. Smith?" |
| `total_trials` | "How many trials has Dr. Smith been involved in?" |

---

## Open Questions

1. **Voyage API key**: Need to obtain for embedding generation
2. **Semantic Scholar API key**: Already have (in .env), confirm still valid
3. **Institution classification accuracy**: May need manual review for top sites
