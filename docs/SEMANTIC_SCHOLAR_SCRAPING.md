# ORCID + Semantic Scholar Data Enrichment

This document describes how to enrich investigator profiles with publication data using ORCID and Semantic Scholar APIs.

> **Note**: This is **Phase 2** of the V2 Data Enrichment Plan. See `V2_DATA_ENRICHMENT_PLAN.md` for the full workflow.

---

## Rollout Strategy: Subset First → Full Production

We validate enrichment on a **subset** before running on the full dataset.

### Phase A: Subset Testing (Current)

**Target**: Investigators linked to diabetes, breast cancer, and obesity trials (~15K investigators)

```
1. Run enrichment on subset only
2. Validate match rates and data quality
3. Test search with enriched data
4. If successful → proceed to Phase B
```

**Script**: `scripts/v2_test/03_enrich_subset_pis.py`

### Phase B: Production Rollout (After Validation)

**Target**: All investigators (~738K)

```
1. Run full enrichment (estimated ~1.5 hours)
2. Compute derived fields
3. Generate embeddings
4. Update production search
```

**Script**: `scripts/enrich_investigators_s2.py`

---

## Overview

**Goal**: Enhance PI recommendations by adding academic publication metrics (h-index, paper count, research areas) to the `investigators` table.

**Data Sources**: 
- [ORCID Public API](https://info.orcid.org/documentation/api-tutorials/) - For high-confidence researcher identification
- [Semantic Scholar Academic Graph API](https://api.semanticscholar.org/api-docs/graph) - For publication metrics

**Expected Outcome**:
- **70-85% of real PIs matched** (up from 40-60% with S2 alone)
- h-index, citation count, and research areas for **scoring and filtering**
- affiliations_s2, notable_papers, research_areas for **tool calling** (answering user questions)
- orcid_id stored for future lookups and verification

---

## Prerequisites

### 1. Get API Keys (Required)

**Semantic Scholar API Key**:
- Without key: 100 requests per 5 minutes (~61 days for 738K investigators)
- With key: 100 requests/second (~30-45 minutes total)
- Get free key: https://www.semanticscholar.org/product/api#api-key-form

**ORCID API Credentials**:
- Register for free Public API credentials: https://info.orcid.org/documentation/integration-guide/registering-a-public-api-client/
- Get client_id and client_secret
- Token lasts ~20 years

### 2. Add to Environment

```bash
# .env
SEMANTIC_SCHOLAR_API_KEY=your_api_key_here

# ORCID API (for high-confidence matching)
ORCID_CLIENT_ID=your_client_id_here
ORCID_CLIENT_SECRET=your_client_secret_here
```

### 3. Install Dependencies

```bash
pip install aiohttp rapidfuzz tenacity
```

---

## Database Schema Changes

Run this migration before scraping:

```sql
-- migrations/007_semantic_scholar_columns.sql

-- Add ORCID + Semantic Scholar enrichment columns to investigators
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS orcid_id VARCHAR(20);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS semantic_scholar_id VARCHAR(20);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS h_index INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS paper_count INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS citation_count INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS affiliations_s2 TEXT[];
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS research_areas TEXT[];
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS notable_papers JSONB;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_match_confidence DECIMAL(3,2);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_match_source VARCHAR(20);  -- 'orcid', 's2_affiliation', 's2_topics'
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_enriched_at TIMESTAMPTZ;

-- Indexes for filtering/sorting
CREATE INDEX IF NOT EXISTS idx_investigators_orcid ON investigators(orcid_id) WHERE orcid_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_investigators_h_index ON investigators(h_index) WHERE h_index IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_investigators_s2_id ON investigators(semantic_scholar_id) WHERE semantic_scholar_id IS NOT NULL;
```

---

## API Endpoints Used

### 1. ORCID Search (Step 1 - High Confidence)

**Get access token** (one-time, lasts ~20 years):
```bash
curl -X POST https://orcid.org/oauth/token \
  -H "Accept: application/json" \
  -d "client_id=YOUR_CLIENT_ID" \
  -d "client_secret=YOUR_CLIENT_SECRET" \
  -d "grant_type=client_credentials" \
  -d "scope=/read-public"
```

**Search by name + affiliation**:
```
GET https://pub.orcid.org/v3.0/search/?q=family-name:Smith+AND+given-names:John+AND+affiliation-org-name:"Harvard Medical School"
Authorization: Bearer {access_token}
Accept: application/json
```

**Response**:
```json
{
  "num-found": 3,
  "result": [
    {
      "orcid-identifier": {
        "uri": "https://orcid.org/0000-0002-1825-0097",
        "path": "0000-0002-1825-0097"
      }
    }
  ]
}
```

### 2. S2 Lookup by ORCID (Preferred)

Once we have an ORCID, we can directly lookup the S2 profile:

```
GET https://api.semanticscholar.org/graph/v1/author/ORCID:0000-0002-1825-0097
?fields=authorId,name,affiliations,paperCount,citationCount,hIndex,papers.title,papers.citationCount
```

This is **much more reliable** than name-based search.

### 3. S2 Author Search (Fallback)

If no ORCID found, fall back to name search:

```
GET https://api.semanticscholar.org/graph/v1/author/search
?query=John+Smith
&fields=authorId,name,affiliations,paperCount,hIndex
&limit=10
```

**Response**:
```json
{
  "total": 1234,
  "data": [
    {
      "authorId": "1741101",
      "name": "John Smith",
      "affiliations": ["Harvard Medical School"],
      "paperCount": 127,
      "hIndex": 45
    }
  ]
}
```

### 4. S2 Author Batch Lookup

Get full details for up to 1000 authors at once:

```
POST https://api.semanticscholar.org/graph/v1/author/batch
?fields=authorId,name,affiliations,paperCount,citationCount,hIndex,papers.title,papers.citationCount

Body: {"ids": ["1741101", "2341234", ...]}
```

**Response**:
```json
[
  {
    "authorId": "1741101",
    "name": "John Smith",
    "affiliations": ["Harvard Medical School"],
    "paperCount": 127,
    "citationCount": 8432,
    "hIndex": 45,
    "papers": [
      {"title": "Novel CAR-T therapy...", "citationCount": 234}
    ]
  }
]
```

---

## Scraping Strategy

### Phase 1: Filter Real PIs

Not all 738K investigators are real PIs. Many are sponsors, coordinators, or organizations.

```sql
-- Get investigators worth enriching
SELECT id, full_name, affiliation 
FROM investigators 
WHERE 
  -- Has name-like pattern
  (full_name ~ '[A-Z][a-z]+.*[A-Z][a-z]+' 
   OR full_name LIKE '%,%')
  -- Has credentials
  AND (full_name LIKE '%MD%' 
       OR full_name LIKE '%PhD%' 
       OR full_name LIKE '%Prof%'
       OR full_name LIKE '%Dr.%'
       OR full_name LIKE '%M.D.%')
  -- Not already enriched
  AND s2_enriched_at IS NULL
  -- Not a known sponsor pattern
  AND full_name !~* '(clinical|pharma|inc|llc|ltd|center|centre|trials|gsk|pfizer|novartis|merck)'
ORDER BY id
LIMIT 100000;
```

**Expected**: ~50-100K real PIs

### Phase 2: ORCID Lookup (High Confidence)

For each investigator, try ORCID first:

```python
async def search_orcid(given_name: str, family_name: str, affiliation: str) -> str | None:
    """
    Search ORCID by name + affiliation.
    Returns ORCID ID if found with high confidence.
    """
    # Build query
    query_parts = [f'family-name:"{family_name}"', f'given-names:"{given_name}"']
    if affiliation:
        # Clean affiliation for search
        clean_aff = affiliation.split(',')[0].strip()  # Take first part
        query_parts.append(f'affiliation-org-name:"{clean_aff}"')
    
    query = " AND ".join(query_parts)
    
    response = await http_client.get(
        f"https://pub.orcid.org/v3.0/search/?q={query}",
        headers={
            "Authorization": f"Bearer {ORCID_TOKEN}",
            "Accept": "application/json"
        }
    )
    
    data = response.json()
    
    # If exactly 1 result, high confidence match
    if data.get("num-found") == 1:
        return data["result"][0]["orcid-identifier"]["path"]
    
    # If 2-3 results, could still be valid - return first
    if 1 < data.get("num-found", 0) <= 3:
        return data["result"][0]["orcid-identifier"]["path"]
    
    return None
```

### Phase 3: S2 Lookup (via ORCID or Name)

```python
async def get_s2_profile(orcid_id: str = None, name: str = None, affiliation: str = None) -> dict | None:
    """
    Get S2 profile. Prefer ORCID lookup, fall back to name search.
    """
    # Method 1: Direct ORCID lookup (high confidence)
    if orcid_id:
        response = await http_client.get(
            f"https://api.semanticscholar.org/graph/v1/author/ORCID:{orcid_id}",
            params={"fields": "authorId,name,affiliations,paperCount,citationCount,hIndex,papers.title,papers.citationCount"},
            headers={"x-api-key": S2_API_KEY}
        )
        if response.status_code == 200:
            return {"profile": response.json(), "source": "orcid", "confidence": 0.95}
    
    # Method 2: Name search with affiliation matching (medium confidence)
    if name:
        response = await http_client.get(
            "https://api.semanticscholar.org/graph/v1/author/search",
            params={"query": name, "fields": "authorId,name,affiliations,paperCount,hIndex", "limit": 10},
            headers={"x-api-key": S2_API_KEY}
        )
        if response.status_code == 200:
            candidates = response.json().get("data", [])
            best_match, confidence = match_by_affiliation(affiliation, candidates)
            if best_match and confidence > 0.7:
                return {"profile": best_match, "source": "s2_affiliation", "confidence": confidence}
    
    return None
```

### Phase 4: Affiliation Matching (for S2 Fallback)

For S2 name search results, fuzzy match affiliation:

```python
def match_by_affiliation(affiliation: str, candidates: list) -> tuple[dict, float]:
    """
    Match CT.gov investigator to Semantic Scholar author by affiliation.
    Returns (best_match, confidence_score) or (None, 0).
    """
    from rapidfuzz import fuzz
    
    best_match = None
    best_score = 0
    
    for candidate in candidates:
        # Name similarity (0-1)
        name_score = fuzz.ratio(
            normalize_name(name), 
            normalize_name(candidate["name"])
        ) / 100
        
        # Affiliation similarity (0-1)
        aff_score = 0
        if affiliation and candidate.get("affiliations"):
            aff_score = max(
                fuzz.partial_ratio(affiliation.lower(), aff.lower()) / 100
                for aff in candidate["affiliations"]
            )
        elif not affiliation:
            aff_score = 0.5  # Neutral if no affiliation to compare
        
        # Combined score (affiliation weighted higher)
        score = 0.4 * name_score + 0.6 * aff_score
        
        if score > best_score:
            best_match = candidate
            best_score = score
    
    # Only return if confidence threshold met
    if best_score >= 0.7:
        return best_match, best_score
    return None, 0


def normalize_name(name: str) -> str:
    """Normalize name for comparison."""
    import re
    # Remove credentials
    name = re.sub(r'\b(MD|PhD|Dr|Prof|MBBS|FRCP|M\.D\.|Ph\.D\.)\b', '', name, flags=re.I)
    # Remove punctuation
    name = re.sub(r'[^\w\s]', ' ', name)
    # Normalize whitespace
    name = ' '.join(name.split())
    return name.lower().strip()
```

### Phase 3: Batch Fetch and Update

```python
async def enrich_investigators_batch(investigator_ids: list[str]) -> int:
    """
    Fetch full profiles for matched S2 authors and update database.
    """
    # Batch fetch from S2 (up to 1000 at a time)
    profiles = await s2_batch_fetch(
        investigator_ids,
        fields="authorId,name,affiliations,paperCount,citationCount,hIndex,papers.title,papers.citationCount"
    )
    
    # Update database
    updated = 0
    for profile in profiles:
        # Extract top 5 papers by citations
        papers = sorted(
            profile.get("papers", []), 
            key=lambda p: p.get("citationCount", 0), 
            reverse=True
        )[:5]
        
        # Extract research areas from paper titles (simple keyword extraction)
        research_areas = extract_research_areas(papers)
        
        # Update investigator record
        await update_investigator(
            s2_id=profile["authorId"],
            h_index=profile.get("hIndex"),
            paper_count=profile.get("paperCount"),
            citation_count=profile.get("citationCount"),
            affiliations_s2=profile.get("affiliations"),
            research_areas=research_areas,
            notable_papers=papers,
        )
        updated += 1
    
    return updated
```

---

## Time Estimates

| Phase | Records | Rate | Time |
|-------|---------|------|------|
| Filter real PIs | 738K → ~80K | Local | ~1 min |
| ORCID search | 80K | ~10/sec | ~2.5 hours |
| S2 lookup (via ORCID) | ~25K matched | 100/sec | ~5 min |
| S2 name search (fallback) | ~55K remaining | 100/sec | ~10 min |
| Match affiliations | 55K | Local | ~1 min |
| Batch fetch full profiles | ~60K matched | 100/sec | ~10 min |
| Update database | ~60K | 500/sec | ~2 min |
| Buffer/retries | - | - | ~15 min |
| **Total** | | | **~3-4 hours** |

**Note**: ORCID adds time but significantly improves match quality (70-85% vs 40-60%).

**Without API keys**: Not recommended (~weeks)

---

## Running the Scraper

```bash
# Set environment variables
export SEMANTIC_SCHOLAR_API_KEY=your_key_here
export ORCID_CLIENT_ID=your_client_id
export ORCID_CLIENT_SECRET=your_client_secret

# Run the enrichment script with ORCID + S2
PYTHONPATH=. python scripts/enrich_investigators_s2.py \
  --limit 100000 \
  --batch-size 100 \
  --resume
```

### Options

| Flag | Description | Default |
|------|-------------|---------|
| `--limit` | Max investigators to process | 100000 |
| `--batch-size` | Investigators per batch | 100 |
| `--resume` | Skip already enriched | True |
| `--dry-run` | Search only, don't update DB | False |
| `--min-confidence` | Match threshold | 0.7 |
| `--use-orcid` | Enable ORCID lookup (recommended) | True |
| `--skip-orcid` | Skip ORCID, use S2 only | False |

### Progress Tracking

The script saves progress to `s2_enrichment_checkpoint.json`:

```json
{
  "last_processed_id": 45678,
  "total_processed": 12000,
  "total_matched": 7200,
  "total_failed": 4800,
  "started_at": "2024-01-15T10:00:00Z",
  "updated_at": "2024-01-15T10:15:00Z"
}
```

---

## Expected Results

| Metric | Expected |
|--------|----------|
| Real PIs identified | ~80K (from 738K) |
| ORCID matches | ~25K (30% of real PIs) |
| S2 via ORCID | ~24K (95% of ORCID matches) |
| S2 via name search | ~35K (65% of remaining) |
| **Total matched** | **~60K (75% match rate)** |
| Average h-index | ~15-25 |
| Average paper count | ~30-50 |

### Match Rate by Source

| Source | Match Rate | Confidence |
|--------|------------|------------|
| ORCID → S2 | 25-35% | **High (90%+)** |
| S2 name + affiliation | 35-45% | Medium (70-85%) |
| **Combined** | **70-85%** | Mixed |

### Match Rate by Credential

| Credential | Expected Match Rate |
|------------|---------------------|
| MD, PhD | ~80-90% |
| Prof, Dr | ~70-80% |
| No credential | ~40-50% |

---

## Post-Enrichment (Next Steps)

After S2 enrichment is complete, proceed to **Phase 3** of the V2 plan:

### 1. Compute Derived Fields

Run the SQL in `V2_DATA_ENRICHMENT_PLAN.md` Phase 3 to compute:
- `therapeutic_areas` (from linked trials)
- `total_trials`, `years_active`, `primary_role`
- Site `institution_type` classification

### 2. Cache Trial Fields for Embedding

```sql
-- Cache intervention_names, lead_pi_name, lead_site_names on trials table
-- See V2_DATA_ENRICHMENT_PLAN.md Phase 3.4
```

### 3. Generate Embeddings (Phase 4)

**Important**: We do NOT generate separate PI embeddings. Instead:
- PI/site context is included in the **trial embedding text**
- S2 fields (`h_index`, `total_trials`) are used for **scoring/ranking**
- S2 fields (`affiliations_s2`, `notable_papers`) are used for **tool calling**

See `V2_DATA_ENRICHMENT_PLAN.md` Phase 4 for embedding generation.

### 4. Update Recommendation Scoring

Add h-index to the scoring formula:

```python
# In recommender.py
final_score = (
    0.50 * semantic_similarity +
    0.20 * experience_score +       # total_trials (log scale)
    0.15 * h_index_score +          # h_index / 50 (capped at 1.0)
    0.15 * role_score               # PI > Study Director > Sub-Investigator
)
```

### 5. Add Filters to API

```python
# In api/routes/recommendations.py
@router.post("/recommendations")
async def get_recommendations(
    query: str,
    min_h_index: int = None,        # Filter by academic reputation
    institution_type: str = None,   # Filter by site type
    ...
):
```

---

## Troubleshooting

### Rate Limit Errors (429)

```python
# The script handles this automatically with exponential backoff
# If persistent, reduce concurrency:
python scripts/enrich_investigators_s2.py --concurrency 50
```

### Low Match Rate

If match rate is below 40%:
1. Lower confidence threshold: `--min-confidence 0.6`
2. Check affiliation data quality in your DB
3. Some clinical PIs don't publish academically (expected)

### Timeout Errors

```python
# Increase timeout in script
S2_TIMEOUT = 30  # seconds (default: 10)
```

---

## Files

| File | Purpose |
|------|---------|
| `scripts/enrich_investigators_s2.py` | Main scraping script |
| `src/enrichment/s2_client.py` | S2 API client |
| `src/enrichment/matcher.py` | Name/affiliation matching |
| `supabase/migrations/007_semantic_scholar_columns.sql` | Schema changes |

---

## References

- [Semantic Scholar API Docs](https://api.semanticscholar.org/api-docs/graph)
- [API Tutorial](https://www.semanticscholar.org/product/api/tutorial)
- [Rate Limits](https://api.semanticscholar.org/api-docs/graph#tag/Rate-Limits)
