# Semantic Scholar Data Enrichment

This document describes how to enrich investigator profiles with publication data from the Semantic Scholar API.

## Overview

**Goal**: Enhance PI recommendations by adding academic publication metrics (h-index, paper count, research areas) to the `investigators` table.

**Data Source**: [Semantic Scholar Academic Graph API](https://api.semanticscholar.org/api-docs/graph)

**Expected Outcome**:
- ~40-60% of real PIs matched to S2 profiles
- h-index, citation count, and research areas for ranking
- Expertise embeddings for semantic search

---

## Prerequisites

### 1. Get an API Key (Required)

Without an API key, you're limited to 100 requests per 5 minutes (~61 days for 738K investigators).

**With an API key**: 100 requests/second (~30-45 minutes total)

Get your free API key: https://www.semanticscholar.org/product/api#api-key-form

### 2. Add to Environment

```bash
# .env
SEMANTIC_SCHOLAR_API_KEY=your_api_key_here
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

-- Add Semantic Scholar enrichment columns to investigators
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS semantic_scholar_id VARCHAR(20);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS h_index INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS paper_count INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS citation_count INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS affiliations_s2 TEXT[];
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS research_areas TEXT[];
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS notable_papers JSONB;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_match_confidence DECIMAL(3,2);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_enriched_at TIMESTAMPTZ;

-- Indexes for filtering/sorting
CREATE INDEX IF NOT EXISTS idx_investigators_h_index ON investigators(h_index);
CREATE INDEX IF NOT EXISTS idx_investigators_s2_id ON investigators(semantic_scholar_id);
CREATE INDEX IF NOT EXISTS idx_investigators_research_areas ON investigators USING GIN(research_areas);
```

---

## API Endpoints Used

### 1. Author Search
Find authors by name.

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

### 2. Author Batch Lookup
Get full details for up to 1000 authors at once.

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
      {"title": "Novel CAR-T therapy...", "citationCount": 234},
      ...
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

### Phase 2: Search and Match

For each investigator:

1. **Search S2 by name** → Get candidate authors
2. **Fuzzy match affiliation** → Find best match
3. **Score confidence** → Only accept matches > 0.7

```python
def match_investigator(name: str, affiliation: str, candidates: list) -> tuple[dict, float]:
    """
    Match CT.gov investigator to Semantic Scholar author.
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
| Search by name | 80K | 100/sec | ~15 min |
| Match affiliations | 80K | Local | ~1 min |
| Batch fetch profiles | ~40K matched | 100/sec | ~7 min |
| Update database | ~40K | 500/sec | ~2 min |
| Buffer/retries | - | - | ~10 min |
| **Total** | | | **~35-45 min** |

**Without API key**: ~5-7 days (not recommended)

---

## Running the Scraper

```bash
# Set environment variable
export SEMANTIC_SCHOLAR_API_KEY=your_key_here

# Run the enrichment script
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
| S2 matches found | ~40K (50% match rate) |
| Average h-index | ~15-25 |
| Average paper count | ~30-50 |

### Match Rate by Credential

| Credential | Expected Match Rate |
|------------|---------------------|
| MD, PhD | ~60-70% |
| Prof, Dr | ~50-60% |
| No credential | ~20-30% |

---

## Post-Enrichment

### 1. Generate Expertise Embeddings

After enrichment, generate embeddings for matched investigators:

```python
def build_expertise_text(inv: dict) -> str:
    """Build text for expertise embedding."""
    parts = [inv["full_name"]]
    
    if inv.get("research_areas"):
        parts.append(f"Research: {', '.join(inv['research_areas'])}")
    
    if inv.get("notable_papers"):
        titles = [p["title"] for p in inv["notable_papers"][:3]]
        parts.append(f"Publications: {'; '.join(titles)}")
    
    if inv.get("affiliations_s2"):
        parts.append(f"Affiliations: {', '.join(inv['affiliations_s2'])}")
    
    return " ".join(parts)
```

### 2. Update Recommendation Scoring

Add h-index to the scoring formula:

```python
# In recommender.py
final_score = (
    0.35 * semantic_similarity +
    0.20 * experience_score +       # trial count
    0.15 * completion_rate +
    0.15 * h_index_score +          # NEW: h_index / 50 (capped at 1.0)
    0.15 * link_confidence
)
```

### 3. Add Filters to API

```python
# In api/routes/recommendations.py
@router.post("/recommendations")
async def get_recommendations(
    query: str,
    min_h_index: int = None,        # NEW
    min_paper_count: int = None,    # NEW
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
