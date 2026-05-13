# V2 Test Scripts

This directory contains scripts for testing the V2 data enrichment approach on a subset of trials before production rollout.

## Subset Definition

**Conditions**: Diabetes, Breast Cancer, Obesity
- ~30K trials
- ~15K investigators

## Scripts

| Script | Purpose |
|--------|---------|
| `01_setup_test_tables.py` | Create test embedding table and search function |
| `02_get_subset_trials.py` | Filter trials by condition, get linked investigators |
| `03_enrich_subset_pis.py` | Run ORCID + S2 enrichment on subset investigators |
| `04_compute_derived_fields.py` | Compute therapeutic_areas, total_trials, etc. |
| `05_generate_embeddings.py` | Generate Voyage-3.5-lite embeddings for subset |
| `06_test_search.py` | Test search queries, compare V1 vs V2 |

## Prerequisites

1. **Run migration** (in Supabase SQL Editor):
```sql
-- Add ORCID and match source columns
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS orcid_id VARCHAR(20);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_match_source VARCHAR(20);
CREATE INDEX IF NOT EXISTS idx_investigators_orcid ON investigators(orcid_id) WHERE orcid_id IS NOT NULL;
```

2. **Add API keys to .env**:
```bash
SEMANTIC_SCHOLAR_API_KEY=your_key
ORCID_CLIENT_ID=your_client_id
ORCID_CLIENT_SECRET=your_client_secret
VOYAGE_API_KEY=your_voyage_key  # For embeddings
```

## Usage

Run scripts in order:

```bash
# 1. Setup test tables in Supabase
PYTHONPATH=. python scripts/v2_test/01_setup_test_tables.py

# 2. Get subset trials and investigators
PYTHONPATH=. python scripts/v2_test/02_get_subset_trials.py

# 3. Enrich subset investigators with ORCID + S2
PYTHONPATH=. python scripts/v2_test/03_enrich_subset_pis.py

# 4. Compute derived fields
PYTHONPATH=. python scripts/v2_test/04_compute_derived_fields.py

# 5. Generate embeddings (requires Voyage API key)
PYTHONPATH=. python scripts/v2_test/05_generate_embeddings.py

# 6. Test search
PYTHONPATH=. python scripts/v2_test/06_test_search.py
```

## Isolation

These scripts use **separate test tables** and do not affect production:

| Production | Test |
|------------|------|
| `trials_embeddings` | `trials_embeddings_v2_test` |
| `search_trials()` | `search_trials_v2_test()` |

The production app continues to use the original tables/functions.
