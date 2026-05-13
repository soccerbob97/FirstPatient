# FirstPatient — Technical Implementation Plan

**Date**: May 3, 2026  
**Product**: Protocol-Conditioned Execution Intelligence  
**Goal**: Build the execution scoring engine that powers PI + Site ranking for clinical trial feasibility

---

## Vision

**Clinical trials fail operationally long before they fail scientifically.**

FirstPatient helps sponsors and specialty CROs determine which sites and PIs can execute a specific protocol successfully before committing time and capital. Unlike competitors who optimize for site history (Citeline), patient availability (TriNetX), or enterprise workflows (Advarra/IQVIA), we answer:

> **"Given this specific protocol, which PI-site pairs can operationally execute it best?"**

---

## Our Wedge

| Competitor | Optimizes For | Gap |
|------------|---------------|-----|
| **Citeline** | Investigator discovery | Database-first, not protocol-first |
| **Advarra** | Workflow + operational feasibility | Services-driven, intelligence-light |
| **IQVIA** | Enterprise feasibility ops | Expensive, black-box, large pharma only |
| **TriNetX** | Patient population feasibility | Weak PI/site execution scoring |
| **Deep 6 AI** | Patient recruitment | Strong protocol parsing, weak site selection |

**Our positioning**: Protocol-first ranking → Site + PI + Execution Fit

**Positioning statement**: *Advarra operationalizes feasibility. Citeline indexes investigators. IQVIA scales enterprise feasibility. FirstPatient predicts protocol-specific execution success.*

---

## Product Architecture

| Layer | What It Does | Status |
|-------|--------------|--------|
| **Layer 1: Protocol Parser** | Convert protocol PDF → structured JSON (I/E criteria, endpoints, visit burden) | Future |
| **Layer 2: Execution Scoring Engine** | Score protocol fit, site fit, PI fit, enrollment fit | **Current focus** |
| **Layer 3: Feasibility Intelligence** | Ranked recommendations + rationale | In progress |

---

## Product Outputs

| Output | Description |
|--------|-------------|
| **Execution Fit Score** | Can this PI-site pair operationally execute this protocol? |
| **Enrollment Fit Score** | Can they recruit the target population? |
| **Operational Risk Score** | What are the execution risks? |
| **Historical Similarity Score** | How similar is this to trials they've run before? |

---

## Current State Summary

| Metric | Value |
|--------|-------|
| **Trials** | 394,214 (after cleanup) |
| **Trials deleted (no PI)** | 183,299 |
| **Investigators enriched** | 3,129 / 12,727 (~25%) |
| **Embedding model** | OpenAI text-embedding-3-small (1536d) |
| **Planned model** | Voyage-3.5-lite (1024d) |

---

## Data Strategy

| Phase | Data Source | Purpose | Status |
|-------|-------------|---------|--------|
| **Now** | ClinicalTrials.gov | Trial history, PI-site relationships | ✅ 394K trials loaded |
| **Now** | PubMed | Recover PIs for deleted trials | 🔄 Planned |
| **Now** | openFDA | Drug MOA, pharmacologic class | 🔄 Planned |
| **Now** | OpenAlex | PI h-index, publications | 🔄 25% complete |
| **Future** | Customer outcomes | Selected sites, enrollment speed, amendments | Feedback table ready |

**Moat loop**: Protocol → Recommendation → Outcome → Better Recommendation

---

## Technical Action Items

### Action Item 1: Recover PI Data for Deleted Trials

#### Problem
You deleted 183,299 trials that lacked PI information in ClinicalTrials.gov. However, many of these trials have published results in journals where the **first author is typically the lead PI**.

### Solution: Multi-Source PI Discovery Pipeline

#### Approach 1: PubMed NCT Number Linking (Recommended - Highest Quality)

**How it works:**
1. Search PubMed for the NCT number
2. Publications mentioning the NCT number often have the PI as first/last author
3. Use PubMed E-utilities API (free, 10 requests/second with API key)

**Implementation:**
```python
import requests

def find_pi_from_pubmed(nct_id: str) -> dict | None:
    """
    Search PubMed for publications mentioning the NCT number.
    First author is typically the lead PI.
    """
    # Step 1: Search PubMed for NCT number
    search_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
    params = {
        "db": "pubmed",
        "term": f"{nct_id}[Secondary Source ID] OR {nct_id}[Title/Abstract]",
        "retmode": "json",
        "retmax": 10,
        "api_key": PUBMED_API_KEY  # Get from NCBI
    }
    
    resp = requests.get(search_url, params=params)
    pmids = resp.json().get("esearchresult", {}).get("idlist", [])
    
    if not pmids:
        return None
    
    # Step 2: Fetch article details
    fetch_url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
        "api_key": PUBMED_API_KEY
    }
    
    # Parse XML to extract first author (typically PI)
    # Return: {"name": "John Smith", "affiliation": "Harvard Medical School", "pmid": "12345678"}
```

**Expected yield**: ~50% of trials have linked publications

#### Approach 2: ClinicalTrials.gov Results Reference Field

**How it works:**
ClinicalTrials.gov has a `results_reference` field that contains publications submitted by investigators.

```python
def get_results_references(nct_id: str) -> list[dict]:
    """
    Fetch results_reference from ClinicalTrials.gov API v2.
    These are investigator-submitted publications.
    """
    url = f"https://clinicaltrials.gov/api/v2/studies/{nct_id}"
    params = {"fields": "ReferencesModule"}
    
    resp = requests.get(url, params=params)
    refs = resp.json().get("referencesModule", {}).get("references", [])
    
    # Filter for results references (not background references)
    return [r for r in refs if r.get("type") == "RESULT"]
```

#### Approach 3: Google Scholar + Journal Scraping (Fallback)

**For trials without PubMed links**, use Google Scholar:

```python
from serpapi import GoogleSearch  # Requires SerpAPI key ($50/mo for 5000 searches)

def find_pi_from_google_scholar(nct_id: str, trial_title: str) -> dict | None:
    """
    Search Google Scholar for trial publications.
    """
    params = {
        "engine": "google_scholar",
        "q": f'"{nct_id}" OR "{trial_title}"',
        "api_key": SERPAPI_KEY
    }
    
    search = GoogleSearch(params)
    results = search.get_dict().get("organic_results", [])
    
    if results:
        # First result's first author is likely the PI
        return {
            "name": results[0].get("publication_info", {}).get("authors", [{}])[0].get("name"),
            "source": "google_scholar",
            "title": results[0].get("title")
        }
```

#### Approach 4: Journal-Specific Scrapers

For high-impact journals (NEJM, Lancet, JAMA), build targeted scrapers:

```python
# Example: New England Journal of Medicine
def scrape_nejm_article(doi: str) -> dict:
    """
    Scrape NEJM article page for author information.
    Note: Respect robots.txt and rate limits.
    """
    url = f"https://www.nejm.org/doi/{doi}"
    # Parse HTML for author list, affiliations
    # First author with "MD" or "PhD" is typically PI
```

### Recommended Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│ For each trial without PI:                                       │
├─────────────────────────────────────────────────────────────────┤
│ 1. Check ClinicalTrials.gov results_reference field              │
│    └─ If found → Extract first author as PI                      │
│                                                                  │
│ 2. Search PubMed for NCT number                                  │
│    └─ If found → Extract first author from publication           │
│                                                                  │
│ 3. Search Google Scholar (if PubMed fails)                       │
│    └─ If found → Extract first author                            │
│                                                                  │
│ 4. Manual review for high-value trials (Phase 3, large sponsors) │
└─────────────────────────────────────────────────────────────────┘
```

### Data Sources Summary

| Source | API | Rate Limit | Cost | Expected Yield |
|--------|-----|------------|------|----------------|
| **PubMed E-utilities** | Free | 10/sec with key | Free | ~50% |
| **ClinicalTrials.gov API v2** | Free | Generous | Free | ~30% |
| **Google Scholar (SerpAPI)** | SerpAPI | 5000/mo | $50/mo | ~20% additional |
| **Journal scrapers** | Custom | Varies | Free | ~10% additional |

### Script Structure

```
scripts/recover_pis/
├── 01_fetch_deleted_trials.py      # Get NCT IDs of deleted trials
├── 02_search_pubmed.py             # PubMed NCT number search
├── 03_search_clinicaltrials.py     # ClinicalTrials.gov results_reference
├── 04_search_google_scholar.py     # Google Scholar fallback
├── 05_import_recovered_pis.py      # Import back into database
└── README.md
```

---

### Action Item 2: Comprehensive Data Enrichment + Improved Embeddings

#### Overview

**Key Principle**: Embeddings are expensive (time + cost). Enrich ALL data first, then embed once.

This action item combines:
1. **PI/Site enrichment** - Add academic metrics, derived fields for scoring and display
2. **Drug/Intervention enrichment** - Add mechanism of action, drug class from openFDA
3. **Single-pass embedding generation** - Generate embeddings after all enrichment is complete

```
┌─────────────────────────────────────────────────────────────────────┐
│ ENRICHMENT PIPELINE (Do ALL before embedding)                       │
├─────────────────────────────────────────────────────────────────────┤
│ Step 2.1: Add schema columns to investigators/sites/trials          │
│ Step 2.2: Enrich investigators via ORCID + Semantic Scholar         │
│ Step 2.3: Enrich interventions via openFDA                          │
│ Step 2.4: Compute derived fields (therapeutic_areas, total_trials)  │
│ Step 2.5: Cache embedding fields on trials table                    │
│ Step 2.6: Generate embeddings (single pass, Voyage-3.5-lite)        │
└─────────────────────────────────────────────────────────────────────┘
```

#### Problem

Current embeddings only include trial title, summary, and conditions. Missing:
- **PI academic metrics** (h-index, publications, affiliations)
- **PI/Site derived fields** (therapeutic_areas, total_trials, institution_type)
- **Mechanism of action** (how the drug works)
- **Drug class** (e.g., GLP-1 agonist, PD-1 inhibitor)
- **Brand names** (Ozempic, Keytruda)

---

#### Step 2.1: Database Schema Changes

##### Investigators Table - New Columns

```sql
-- ============================================
-- FROM ORCID + SEMANTIC SCHOLAR API
-- ============================================
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS orcid_id VARCHAR(20);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS semantic_scholar_id VARCHAR(20);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS h_index INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS paper_count INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS citation_count INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS affiliations_s2 TEXT[];        -- For tool calling
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS notable_papers JSONB;           -- [{title, year, citations}]
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS research_areas TEXT[];          -- For display + tool calling
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_match_confidence DECIMAL(3,2);
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_match_source VARCHAR(20);    -- 'orcid', 's2_affiliation'
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS s2_enriched_at TIMESTAMPTZ;

-- ============================================
-- DERIVED FROM TRIAL HISTORY
-- ============================================
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS therapeutic_areas TEXT[];
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS total_trials INTEGER DEFAULT 0;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS years_active INTEGER;
ALTER TABLE investigators ADD COLUMN IF NOT EXISTS primary_role VARCHAR(50);

-- ============================================
-- INDEXES
-- ============================================
CREATE INDEX IF NOT EXISTS idx_investigators_h_index ON investigators(h_index) WHERE h_index IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_investigators_total_trials ON investigators(total_trials);
```

**Field purposes**:
| Field | Source | Purpose |
|-------|--------|---------|
| `orcid_id` | ORCID API | High-confidence identifier for S2 lookup |
| `h_index` | S2 API | **Filtering + Scoring** |
| `affiliations_s2` | S2 API | **Tool calling** ("Where does Dr. X work?") |
| `notable_papers` | S2 API | **Tool calling** ("What has Dr. X published?") |
| `therapeutic_areas` | Derived | **Display + Tool calling** (NOT for filtering) |
| `total_trials` | Derived | **Scoring** |

##### Sites Table - New Columns

```sql
-- Classification
ALTER TABLE sites ADD COLUMN IF NOT EXISTS institution_type VARCHAR(50);
  -- Values: 'academic_medical_center', 'community_hospital', 'cro', 
  --         'pharma_site', 'private_practice', 'government', 'other'

-- Derived from trial history
ALTER TABLE sites ADD COLUMN IF NOT EXISTS therapeutic_areas TEXT[];
ALTER TABLE sites ADD COLUMN IF NOT EXISTS total_trials INTEGER DEFAULT 0;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS total_investigators INTEGER DEFAULT 0;
ALTER TABLE sites ADD COLUMN IF NOT EXISTS active_since INTEGER;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sites_institution_type ON sites(institution_type);
CREATE INDEX IF NOT EXISTS idx_sites_country ON sites(country);
```

##### Interventions Table - New Columns (openFDA)

```sql
ALTER TABLE interventions ADD COLUMN IF NOT EXISTS mechanism_of_action TEXT;
ALTER TABLE interventions ADD COLUMN IF NOT EXISTS drug_class TEXT;
ALTER TABLE interventions ADD COLUMN IF NOT EXISTS brand_names TEXT[];
ALTER TABLE interventions ADD COLUMN IF NOT EXISTS generic_name VARCHAR(255);
ALTER TABLE interventions ADD COLUMN IF NOT EXISTS fda_enriched_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_interventions_drug_class ON interventions(drug_class);
```

##### Trials Table - Cached Fields for Embedding

```sql
-- Cache for embedding generation (avoids expensive joins)
ALTER TABLE trials ADD COLUMN IF NOT EXISTS intervention_names TEXT[];
ALTER TABLE trials ADD COLUMN IF NOT EXISTS lead_pi_name VARCHAR(255);
ALTER TABLE trials ADD COLUMN IF NOT EXISTS lead_site_names TEXT[];
ALTER TABLE trials ADD COLUMN IF NOT EXISTS embedding_text TEXT;
```

---

#### Step 2.2: PI Enrichment via ORCID + Semantic Scholar

**Goal**: Add h-index, publication data, affiliations for **70-85% of real PIs**.

##### Multi-Source Matching Strategy

```
For each investigator (name, affiliation):

Step 1: Try ORCID first (highest confidence)
   a. Search ORCID API: family-name:{last} AND given-names:{first} AND affiliation-org-name:"{affiliation}"
   b. If ORCID found → Use ORCID to lookup S2 profile: GET /author/ORCID:{orcid_id}
   c. High confidence match (90%+)

Step 2: Fall back to S2 name search (if no ORCID)
   a. Search S2 API by name: GET /author/search?query={name}
   b. Fuzzy match affiliation to CT.gov affiliation
   c. Medium confidence match (70-85%)
```

##### Expected Match Rates

| Strategy | Match Rate | Confidence |
|----------|------------|------------|
| ORCID → S2 lookup | 25-35% | **High (90%+)** |
| S2 name + affiliation | 35-45% | Medium (70-85%) |
| **Combined Total** | **70-85%** | Mixed |

##### API Details

**ORCID API** (free):
| Endpoint | Purpose |
|----------|---------|
| `GET /v3.0/search/?q=...` | Search by name + affiliation |

**Semantic Scholar API**:
| Endpoint | Purpose | Rate Limit |
|----------|---------|------------|
| `GET /author/ORCID:{id}` | Lookup by ORCID (preferred) | 100 req/sec |
| `GET /author/search` | Find author by name | 100 req/sec |
| `POST /author/batch` | Batch lookup (up to 1000) | 100 req/sec |

**S2 Fields to request**:
```
name,affiliations,paperCount,citationCount,hIndex,papers.title,papers.year,papers.citationCount
```

---

#### Step 2.3: Intervention Enrichment via openFDA

**API Endpoint**: `https://api.fda.gov/drug/label.json`

**Key Fields Available**:
| Field | Description | Example |
|-------|-------------|---------|
| `mechanism_of_action` | How the drug works | "Semaglutide is a GLP-1 receptor agonist..." |
| `openfda.brand_name` | Brand names | ["Ozempic", "Wegovy"] |
| `openfda.generic_name` | Generic name | "semaglutide" |
| `openfda.pharm_class_epc` | Pharmacologic class | "Glucagon-Like Peptide-1 (GLP-1) Receptor Agonist" |

```python
import requests

def enrich_intervention_from_fda(drug_name: str) -> dict | None:
    """Fetch drug information from openFDA."""
    url = "https://api.fda.gov/drug/label.json"
    params = {
        "search": f'openfda.brand_name:"{drug_name}" OR openfda.generic_name:"{drug_name}"',
        "limit": 1
    }
    
    resp = requests.get(url, params=params)
    if resp.status_code != 200:
        return None
    
    results = resp.json().get("results", [])
    if not results:
        return None
    
    label = results[0]
    return {
        "mechanism_of_action": label.get("mechanism_of_action", [None])[0],
        "brand_names": label.get("openfda", {}).get("brand_name", []),
        "generic_name": label.get("openfda", {}).get("generic_name", [None])[0],
        "pharm_class": label.get("openfda", {}).get("pharm_class_epc", []),
    }
```

**Other Drug Data Sources to Consider**:
| Source | Data Available | API | Cost |
|--------|----------------|-----|------|
| **openFDA** | MOA, drug class, indications | Yes | Free |
| **DrugBank** | Detailed pharmacology, targets | Yes | $$$$ (enterprise) |
| **ChEMBL** | Bioactivity, targets | Yes | Free |
| **PubChem** | Chemical structure, bioassays | Yes | Free |
| **RxNorm** | Drug relationships, NDC codes | Yes | Free |

**Recommendation**: Start with openFDA (free, comprehensive). Add ChEMBL for target/pathway data if needed.

---

#### Step 2.4: Compute Derived Fields

Run these **after** S2 enrichment is complete:

##### Investigator Derived Fields
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
```

##### Site Derived Fields
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

-- Institution type classification
UPDATE sites
SET institution_type = CASE
    WHEN facility_name ~* '(university|medical school|academic|teaching hospital)' THEN 'academic_medical_center'
    WHEN facility_name ~* '(community|regional|general hospital)' THEN 'community_hospital'
    WHEN facility_name ~* '(cro|contract research)' THEN 'cro'
    WHEN facility_name ~* '(pharma|pharmaceutical|inc\.|llc)' THEN 'pharma_site'
    WHEN facility_name ~* '(private|clinic|practice)' THEN 'private_practice'
    WHEN facility_name ~* '(va |veterans|nih|cdc|government)' THEN 'government'
    ELSE 'other'
END
WHERE institution_type IS NULL;
```

---

#### Step 2.5: Cache Trial Fields for Embedding

```sql
-- Cache intervention names
UPDATE trials t
SET intervention_names = subq.names
FROM (
    SELECT trial_id, ARRAY_AGG(DISTINCT name) AS names
    FROM interventions WHERE name IS NOT NULL
    GROUP BY trial_id
) subq
WHERE t.id = subq.trial_id;

-- Cache lead PI name
UPDATE trials t
SET lead_pi_name = subq.pi_name
FROM (
    SELECT DISTINCT ON (trial_id)
        ti.trial_id, i.full_name AS pi_name
    FROM trial_investigators ti
    JOIN investigators i ON ti.investigator_id = i.id
    WHERE ti.role IN ('PRINCIPAL_INVESTIGATOR', 'STUDY_DIRECTOR')
    ORDER BY trial_id, CASE ti.role WHEN 'PRINCIPAL_INVESTIGATOR' THEN 1 ELSE 2 END
) subq
WHERE t.id = subq.trial_id;
```

---

#### Step 2.6: Generate Embeddings (Single Pass)

##### Embedding Text Construction

**Key decisions:**
- ✅ **Include PI names** - Enables "Find trials by Dr. X" queries
- ❌ **Exclude site names** - Site names add noise; use structured metadata filtering instead
- ✅ **Include mechanism of action** - Enables drug class matching ("GLP-1 agonist")
- ✅ **Include drug class** - Enables pharmacologic queries ("immunotherapy")

```python
def build_trial_embedding_text(trial: dict) -> str:
    parts = []
    
    # Core trial info
    if trial.get("brief_title"):
        parts.append(f"Title: {trial['brief_title']}")
    
    if trial.get("brief_summary"):
        summary = trial["brief_summary"][:800]
        parts.append(f"Summary: {summary}")
    
    if trial.get("conditions"):
        conditions = trial["conditions"] if isinstance(trial["conditions"], list) else [trial["conditions"]]
        parts.append(f"Conditions: {', '.join(conditions[:10])}")
    
    if trial.get("phase"):
        parts.append(f"Phase: {trial['phase']}")
    
    # Drug/intervention details
    if trial.get("intervention_names"):
        parts.append(f"Interventions: {', '.join(trial['intervention_names'][:5])}")
    
    if trial.get("mechanism_of_action"):
        moa = trial["mechanism_of_action"][:300]
        parts.append(f"Mechanism: {moa}")
    
    if trial.get("drug_class"):
        parts.append(f"Drug class: {trial['drug_class']}")
    
    # Lead PI (for "Find trials by Dr. X" queries)
    if trial.get("lead_pi_name"):
        parts.append(f"Lead Investigator: {trial['lead_pi_name']}")
    
    return " ".join(parts)
```

##### Embedding Model Choice

| Model | Dimensions | Cost | Quality |
|-------|------------|------|---------|
| OpenAI text-embedding-3-small | 1536 | $0.02/1M tokens | Baseline |
| **Voyage-3.5-lite** | 1024 | $0.02/1M tokens | +6.34% better |

**Recommendation**: Use **Voyage-3.5-lite with 1024 dimensions**
- Same cost as OpenAI
- Better quality
- 33% smaller vectors = less storage, faster search

---

#### Script Structure

```
scripts/enrich/
├── 01_add_schema_columns.py        # Add new columns to tables
├── 02_enrich_pis_orcid_s2.py       # ORCID + Semantic Scholar enrichment
├── 03_enrich_interventions_fda.py  # openFDA drug enrichment
├── 04_compute_derived_fields.py    # therapeutic_areas, total_trials, etc.
├── 05_cache_embedding_fields.py    # Cache intervention_names, lead_pi, etc.
├── 06_generate_embeddings.py       # Voyage-3.5-lite embeddings
└── README.md
```

---

#### Implementation Timeline

| Step | Task | Effort | Dependencies |
|------|------|--------|--------------|
| 2.1 | Add schema columns | 30 min | None |
| 2.2 | PI enrichment (ORCID + S2) | 2-4 hours | Step 2.1 |
| 2.3 | Intervention enrichment (openFDA) | 1-2 hours | Step 2.1 |
| 2.4 | Compute derived fields | 1 hour | Steps 2.2, 2.3 |
| 2.5 | Cache embedding fields | 30 min | Step 2.4 |
| 2.6 | Generate embeddings | 2-4 hours | Step 2.5 |
| **Total** | | **~8-12 hours** | |

---

#### Supported Queries After Enrichment

| Query Type | How It Works |
|------------|--------------|
| "Find PI for Keytruda trial" | Drug name in embedding → semantic match |
| "Oncology trials in Germany" | Conditions in embedding + country filter |
| "Experienced oncology PI" | Semantic match + rank by h_index/total_trials |
| "Academic medical centers in Germany" | Metadata filter: institution_type + country |
| "Tell me about Dr. Smith" | **Tool calling** → fetch affiliations_s2, notable_papers |
| "What has Dr. Smith published?" | **Tool calling** → fetch notable_papers JSONB |

---

#### Tool Calling Support

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

### Action Item 3: Data-Driven Execution Scoring with PCA

#### Problem
Current scoring formula uses **arbitrary weights**:
- 60% semantic similarity
- 15% experience (trial count)
- 10% completion rate (**simulated, not real**)
- 15% role confidence

These weights were chosen without data validation. We need a principled approach to derive **Execution Fit Scores**.

#### Solution: PCA + Correlation Analysis for Feature Selection

Instead of guessing weights, we'll use **historical trial data** to discover which features actually predict execution success.

**Goal**: Derive data-driven weights that map to product outputs:
- **Execution Fit Score** ← completion_rate, phase_experience, site_completion_rate
- **Historical Similarity Score** ← condition_experience, semantic_similarity
- **Enrollment Fit Score** ← recency, site_trial_count
- **Operational Risk Score** ← inverse of above signals

##### Step 1: Define Success Labels

| Field | Success Indicator | How to Use |
|-------|-------------------|------------|
| `overall_status` | COMPLETED vs TERMINATED/WITHDRAWN | Primary label |
| `has_results` | Trial published results | Strong success signal |
| `enrollment` (ACTUAL vs ANTICIPATED) | Met enrollment target | Execution quality |
| `completion_date` vs `primary_completion_date` | On-time completion | Execution quality |

##### Step 2: Build Feature Matrix

For each PI-trial pair, compute these features:

**PI-Level Features**:
| Feature | Description | Source |
|---------|-------------|--------|
| `h_index` | Academic reputation | OpenAlex |
| `total_trials` | Total trials before this one | Derived |
| `completion_rate` | Historical success rate | Derived |
| `years_active` | Career length | Derived |
| `condition_experience` | Trials in this therapeutic area | Derived |
| `phase_experience` | Trials in this phase | Derived |

**Query-Match Features**:
| Feature | Description | Source |
|---------|-------------|--------|
| `semantic_similarity` | Embedding cosine similarity | Vector search |
| `condition_overlap` | % of PI's trials in query condition | Computed |
| `phase_match` | PI has done this phase before (0/1) | Computed |
| `recency` | Days since last trial | Derived |

**Site-Level Features**:
| Feature | Description | Source |
|---------|-------------|--------|
| `site_trial_count` | Site's total trials | Derived |
| `site_completion_rate` | Site's historical success | Derived |
| `institution_type` | Academic vs private | Classification |

##### Step 3: Correlation Analysis (Simple Approach)

Compute correlation of each feature with trial success:

```python
import pandas as pd

# Get completed trials with outcomes
query = """
SELECT 
    t.id as trial_id,
    i.id as investigator_id,
    -- Success label
    CASE WHEN t.overall_status = 'COMPLETED' AND t.has_results = true 
         THEN 1 ELSE 0 END as success,
    -- Features
    i.h_index,
    i.total_trials,
    i.years_active,
    -- ... more features
FROM trials t
JOIN trial_investigators ti ON t.id = ti.trial_id
JOIN investigators i ON ti.investigator_id = i.id
WHERE t.overall_status IN ('COMPLETED', 'TERMINATED', 'WITHDRAWN')
"""

df = pd.read_sql(query, conn)

# Compute correlations with success
feature_cols = ['h_index', 'total_trials', 'years_active', 'completion_rate', 
                'condition_experience', 'phase_experience', 'recency']
correlations = df[feature_cols + ['success']].corr()['success'].drop('success')
print(correlations.sort_values(ascending=False))

# Use correlations as weights (normalized)
weights = correlations.abs() / correlations.abs().sum()
```

**Expected output:**
```
completion_rate       0.42
condition_experience  0.38
h_index               0.31
total_trials          0.27
phase_experience      0.22
years_active          0.14
recency               0.11
```

##### Step 4: PCA for Dimensionality Reduction (Advanced)

Discover latent factors that explain variance:

```python
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA

# Standardize features
X = df[feature_cols].fillna(0)
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# Run PCA
pca = PCA(n_components=0.95)  # Keep 95% variance
X_pca = pca.fit_transform(X_scaled)

print(f"Reduced {len(feature_cols)} features → {pca.n_components_} components")
print(f"Explained variance: {pca.explained_variance_ratio_}")

# Interpret components via loadings
loadings = pd.DataFrame(
    pca.components_.T,
    columns=[f'PC{i+1}' for i in range(pca.n_components_)],
    index=feature_cols
)
print(loadings)
```

**Expected interpretation:**
```
                        PC1      PC2      PC3
h_index                0.45     0.12    -0.08   ← Experience/Reputation
total_trials           0.42     0.15     0.10
years_active           0.38     0.20     0.05
completion_rate        0.35     0.40     0.15   ← Relevance/Track Record
condition_experience   0.10     0.55     0.30
phase_experience       0.05     0.48     0.25
recency               -0.20     0.10     0.60   ← Recency
```

**Latent factors discovered:**
- **PC1** = "Experience/Reputation" (h_index, total_trials, years_active)
- **PC2** = "Relevance" (condition_experience, phase_experience, completion_rate)
- **PC3** = "Recency" (recent activity)

##### Step 5: Apply Data-Driven Weights

```python
def calculate_score_pca(
    features: dict,
    correlation_weights: dict,  # From Step 3
    semantic_similarity: float
) -> float:
    """
    Score using data-driven weights from correlation analysis.
    """
    # Semantic similarity always important (not in historical data)
    score = 0.40 * semantic_similarity
    
    # Add weighted features (weights from correlation analysis)
    for feature, weight in correlation_weights.items():
        if feature in features:
            # Normalize feature to 0-1 range
            normalized = normalize_feature(features[feature], feature)
            score += weight * normalized
    
    return score

# Example with correlation-derived weights:
correlation_weights = {
    'completion_rate': 0.18,       # 0.42 / sum * 0.60
    'condition_experience': 0.16,  # 0.38 / sum * 0.60
    'h_index': 0.13,               # 0.31 / sum * 0.60
    'total_trials': 0.11,          # 0.27 / sum * 0.60
    'phase_experience': 0.09,      # 0.22 / sum * 0.60
    'years_active': 0.06,          # 0.14 / sum * 0.60
    'recency': 0.05,               # 0.11 / sum * 0.60
}
# Note: 0.40 for similarity + 0.60 for features = 1.0
```

#### Phase 2: ML-Based Ranking (When You Have User Feedback)

Once you collect ~1000+ user selections, train a LightGBM ranker:

```python
import lightgbm as lgb

# Prepare ranking data
# group_sizes = number of candidates shown per query
train_data = lgb.Dataset(
    X_train,  # Features: [similarity, h_index, completion_rate, ...]
    label=y_train,  # 1 if user selected, 0 otherwise
    group=group_sizes
)

params = {
    "objective": "lambdarank",
    "metric": "ndcg",
    "ndcg_eval_at": [5, 10],
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 20,
}

model = lgb.train(params, train_data, num_boost_round=100)

# Feature importance tells us what users actually care about
importance = pd.DataFrame({
    'feature': feature_names,
    'importance': model.feature_importance()
}).sort_values('importance', ascending=False)
```

#### Add Feedback Logging Infrastructure

```sql
CREATE TABLE recommendation_feedback (
    id SERIAL PRIMARY KEY,
    query TEXT,
    query_embedding VECTOR(1024),
    query_conditions TEXT[],
    query_phase VARCHAR(20),
    -- What was shown
    shown_results JSONB,  -- [{pi_id, site_id, score, position, features}]
    -- What user did
    selected_pi_id INTEGER,
    selected_site_id INTEGER,
    selected_position INTEGER,
    feedback_type VARCHAR(20),  -- 'click', 'contact', 'shortlist', 'explicit_good'
    -- Metadata
    user_id INTEGER,
    session_id VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for training data extraction
CREATE INDEX idx_feedback_created ON recommendation_feedback(created_at);
CREATE INDEX idx_feedback_type ON recommendation_feedback(feedback_type);
```

#### Implementation Phases

| Phase | Approach | Data Needed | Timeline |
|-------|----------|-------------|----------|
| **Phase 1** | Correlation analysis | Historical trial outcomes | Week 1 |
| **Phase 2** | PCA factor discovery | Same as Phase 1 | Week 1-2 |
| **Phase 3** | Deploy data-driven weights | Phase 1-2 results | Week 2 |
| **Phase 4** | Collect user feedback | Production traffic | Ongoing |
| **Phase 5** | Train LightGBM ranker | ~1000+ selections | Month 2+ |

---

## Product Roadmap Alignment

| Product Phase | Timeline | Technical Work |
|---------------|----------|----------------|
| **Phase 1**: Protocol parser, PI/site ranking | 0-3 months | ✅ Current focus — PI recovery, enrichment, scoring |
| **Phase 2**: Execution fit scoring, feasibility forecasting | 3-6 months | PCA-derived scores, risk flags from protocol complexity |
| **Phase 3**: Outcome ingestion, adaptive refinement | 6-12 months | Feedback loop → LightGBM ranker |

---

## Implementation Priority

| Priority | Action Item | Effort | Impact | Product Layer |
|----------|-------------|--------|--------|---------------|
| **1** | Recover PIs via PubMed/ClinicalTrials.gov | 2-3 days | High (183K trials) | Layer 2: Scoring Engine |
| **2** | Enrich interventions with openFDA | 1-2 days | Medium (protocol-aware matching) | Layer 2: Scoring Engine |
| **3** | Run correlation analysis + PCA | 1-2 days | High (Execution Fit Score) | Layer 2: Scoring Engine |
| **4** | Complete OpenAlex enrichment | Ongoing | Medium (PI reputation) | Layer 2: Scoring Engine |
| **5** | Re-generate embeddings | 1 day | Medium | Layer 3: Intelligence |
| **6** | Add feedback logging | 0.5 days | Future moat | Layer 3: Intelligence |

---

## Next Steps

1. **Create PI recovery scripts** in `scripts/recover_pis/`
2. **Create FDA enrichment script** in `scripts/enrich_fda.py`
3. **Create correlation/PCA analysis script** in `scripts/analyze_features.py`
4. **Update embedding text function** (include MOA, drug class, PI names; exclude site names)
5. **Re-generate embeddings** with enriched data
6. **Update scoring function** with data-driven Execution Fit Score
7. **Add feedback logging** to API (proprietary outcome loop)

---

## Customer Segments

| Segment | Why FirstPatient |
|---------|------------------|
| **Small biotech sponsors** | Limited internal feasibility teams, high execution risk |
| **Specialty CROs** (oncology, rare disease, CNS, metabolic) | Domain expertise but weak internal tooling |
| **Sponsors validating CRO recommendations** | "Validate your CRO's site recommendations before locking execution" |

---

## Business Model

**Feasibility Engagement Model** — priced per study planning cycle, not per search:
- $3k–$5k per feasibility engagement (early)
- Enterprise contracts later
- Optional CRO package: 5–10 feasibility engagements/month

---

## Open Questions

1. **PubMed API key**: Do you have one? (Free from NCBI)
2. **SerpAPI key**: Needed for Google Scholar fallback ($50/mo)
3. **Feedback collection**: How will users provide feedback? (clicks, shortlist, contact)

---

## Appendix: Embedding Content Summary

**Included in embeddings:**
- ✅ Trial title
- ✅ Trial summary (truncated to 800 chars)
- ✅ Conditions
- ✅ Phase
- ✅ Intervention names
- ✅ Mechanism of action (from openFDA)
- ✅ Drug class (from openFDA)
- ✅ Lead PI name

**Excluded from embeddings:**
- ❌ Site names (use structured metadata filtering instead)

---

## Validation Strategy

| Method | Purpose |
|--------|---------|
| **Historical Backtesting** | Run protocols from completed trials, compare recommended sites to actual sites |
| **Expert Validation** | Show feasibility outputs to sponsors/CROs, ask if they would trust the shortlist |
| **Time Savings ROI** | Measure reduction in feasibility cycle time (goal: 3 weeks → 3 days) |
