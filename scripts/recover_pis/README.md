# PI Recovery Pipeline

This directory contains scripts to recover Principal Investigator (PI) data for trials that lack PI information in ClinicalTrials.gov.

## Background

Analysis of `ctg-studies_full.json` (579K trials) shows:
- **493,933 trials (85.3%)** have PI information
- **85,080 trials (14.7%)** have NO PI information

Of the 85K trials without PIs, ~40K are COMPLETED trials that may have publications we can use to identify the PI.

## Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────┐
│ Step 0a: Analyze ctg-studies_full.json                          │
│          Identify trials without PIs                            │
│          Output: trials_without_pi_from_json.json (85K trials)  │
├─────────────────────────────────────────────────────────────────┤
│ Step 0b: Extract references from JSON (optional)                │
│          Check if JSON has result publications                  │
│          Output: recovered_pis_from_json_refs.json              │
├─────────────────────────────────────────────────────────────────┤
│ Step 2a: Test PubMed search on sample (50 trials)               │
│          Verify API works, estimate recovery rate               │
│          Output: test_pubmed_results.json                       │
├─────────────────────────────────────────────────────────────────┤
│ Step 2b: Full PubMed search (85K trials)                        │
│          Search for NCT numbers in publications                 │
│          First author = likely PI                               │
│          Output: recovered_pis_pubmed_full.json                 │
│          Runtime: ~2.5h (with API key) or ~8h (without)         │
├─────────────────────────────────────────────────────────────────┤
│ Step 4: Import recovered PIs into database                      │
│         Create trials, investigators, and links                 │
└─────────────────────────────────────────────────────────────────┘
```

## Usage

### Prerequisites

1. Set up environment variables in `.env`:
   ```
   SUPABASE_URL=your_supabase_url
   SUPABASE_KEY=your_supabase_key
   PUBMED_API_KEY=your_pubmed_api_key  # Optional but recommended
   ```

2. Get a free PubMed API key from: https://www.ncbi.nlm.nih.gov/account/

### Running the Pipeline

```bash
# Step 0a: Analyze JSON to find trials without PIs (already done)
python scripts/recover_pis/00_analyze_ctg_json.py

# Step 2a: Test PubMed on sample first
python scripts/recover_pis/02a_test_pubmed_sample.py

# Step 2b: Full PubMed search (takes 2.5-8 hours)
python scripts/recover_pis/02b_search_pubmed_full.py

# Step 4: Import into database
python scripts/recover_pis/04_import_recovered_pis.py
```

## Expected Results

Based on testing:

| Source | Recovery Rate | Estimated PIs |
|--------|---------------|---------------|
| PubMed (completed trials) | ~18% | ~7,100 |
| PubMed (all trials) | ~10-15% | ~8,500-12,750 |

## Output Files

| File | Description |
|------|-------------|
| `trials_without_pi_from_json.json` | 85K trials without PI |
| `test_pubmed_results.json` | Sample test results |
| `recovered_pis_pubmed_full.json` | PIs found via PubMed |
| `pubmed_search_progress.json` | Resume checkpoint |

## Rate Limits

| API | Rate Limit | Notes |
|-----|------------|-------|
| PubMed (no key) | 3 req/sec | Get a free API key for 10 req/sec |
| PubMed (with key) | 10 req/sec | Free from NCBI |
| ClinicalTrials.gov | ~10 req/sec | Be respectful |

## After Import

After importing recovered PIs, you'll need to:

1. **Generate embeddings** for new trials
2. **Enrich investigators** with OpenAlex (h-index, publications)
3. **Rebuild HNSW index** if you added many trials

## Data Quality Notes

- First author of a publication is **typically** the lead PI, but not always
- Some publications may list the statistician or study coordinator first
- Consider manual review for high-value trials (Phase 3, large sponsors)
