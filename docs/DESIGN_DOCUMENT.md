# Clinical Trial Site Recommender - Design & Implementation Document

**Version:** 1.0  
**Date:** April 2026  
**Status:** Draft

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Problem Statement](#2-problem-statement)
3. [Users & Personas](#3-users--personas)
4. [Requirements](#4-requirements)
5. [System Architecture](#5-system-architecture)
6. [Data Model](#6-data-model)
7. [Core Algorithms](#7-core-algorithms)
8. [API Design](#8-api-design)
9. [Implementation Phases](#9-implementation-phases)
10. [Technical Stack](#10-technical-stack)
11. [Risks & Mitigations](#11-risks--mitigations)
12. [Success Metrics](#12-success-metrics)
13. [Future Roadmap](#13-future-roadmap)

---

## 1. Executive Summary

### Vision

Build an AI-powered system that recommends optimal Principal Investigator (PI) + clinical trial site combinations for biotech sponsors, converting fragmented public clinical trial data into a structured, searchable decision-support tool.

### Core Value Proposition

- **For biotech startups:** Reduce site selection time from weeks to hours
- **For the industry:** Democratize access to trial site intelligence currently locked within CROs
- **Impact:** Reduce drug development delays and costs by improving trial execution success rates

### Key Insight

CROs provide value not because they "find sites," but because they know which PI-site combinations will successfully execute trials. This knowledge is tacit, unstructured, and not publicly accessible. Our system aims to surface this intelligence from public data.

---

## 2. Problem Statement

### Current State

| Challenge | Impact |
|-----------|--------|
| **Manual & slow** | Site selection requires extensive research across multiple fragmented sources |
| **Opaque** | Success depends on CRO relationships and internal knowledge |
| **Data-fragmented** | Relevant information spread across ClinicalTrials.gov, academic papers, FDA releases |
| **High-stakes** | Poor site selection → low enrollment → trial delays → millions in wasted costs |

### Root Cause

CROs/CMOs function as intermediaries between drug sponsors and trial implementers (PIs and trial sites). They possess tacit operational knowledge accumulated through repeated trial execution, but have no incentive to make it legible. **The information asymmetry is their margin.**

### Consequence

Drug development costs ~$3B and takes 10-15 years. Poor sponsor-PI/trial site matching introduces:
- Underenrollment
- Poor data collection
- Trial run-time bloat

### Opportunity

Despite the knowledge monopoly CROs possess, they are misaligned—maximizing client volume instead of P(trial success). An open, data-driven tool can provide better matching at lower cost.

---

## 3. Users & Personas

### Primary Users

#### 3.1 Biotech Startup Founder / CEO
- **Profile:** Early-stage biotech (Series A/B), 5-50 employees
- **Pain Point:** Limited budget for CRO services, needs to make informed site selection decisions quickly
- **Goal:** Find qualified sites for Phase 1-2 trials without expensive CRO contracts
- **Usage Pattern:** Occasional (during trial planning phases)

#### 3.2 Clinical Operations Lead
- **Profile:** Mid-level professional at biotech or pharma company
- **Pain Point:** Spends weeks researching potential sites manually
- **Goal:** Generate shortlist of qualified PI-site combinations for internal review
- **Usage Pattern:** Regular (weekly during active planning)

#### 3.3 Clinical Development Consultant
- **Profile:** Independent consultant advising multiple biotech clients
- **Pain Point:** Needs to provide site recommendations across various therapeutic areas
- **Goal:** Quickly generate evidence-backed recommendations for clients
- **Usage Pattern:** Frequent (multiple times per week)

### Secondary Users

#### 3.4 Academic Researchers
- **Profile:** Researchers studying clinical trial patterns
- **Goal:** Analyze trial site performance and investigator networks
- **Usage Pattern:** Occasional

#### 3.5 Investors / Due Diligence Teams
- **Profile:** VCs evaluating biotech investments
- **Goal:** Assess feasibility of proposed trial plans
- **Usage Pattern:** Occasional

### User Journey (Primary)

```
1. User has a trial concept (indication, phase, geography)
           ↓
2. User enters natural language description
           ↓
3. System parses and structures the query
           ↓
4. System returns ranked PI-site recommendations
           ↓
5. User reviews recommendations with explanations
           ↓
6. User exports shortlist for further evaluation
```

---

## 4. Requirements

### 4.1 Functional Requirements

#### Core Features (MVP)

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| F1 | Natural Language Input | P0 | Accept trial descriptions in plain English |
| F2 | Query Parsing | P0 | Extract structured parameters (indication, phase, location, priorities) |
| F3 | PI-Site Search | P0 | Query database and return matching PI-site combinations |
| F4 | Scoring & Ranking | P0 | Score candidates based on experience, performance, relevance |
| F5 | Results Display | P0 | Show ranked list with scores and key metrics |
| F6 | LLM Explanations | P1 | Generate human-readable reasoning for recommendations |
| F7 | Export | P1 | Export results to CSV/PDF |
| F8 | Filters | P1 | Filter results by geography, experience level, institution type |

#### Data Features

| ID | Feature | Priority | Description |
|----|---------|----------|-------------|
| D1 | ClinicalTrials.gov Ingestion | P0 | Bulk import and parse trial data |
| D2 | Incremental Updates | P1 | Daily/weekly sync of new trials |
| D3 | PI-Site Linking | P0 | Heuristic matching of PIs to sites |
| D4 | Performance Metrics | P0 | Calculate completion rates, trial counts |

### 4.2 Non-Functional Requirements

| Category | Requirement |
|----------|-------------|
| **Performance** | Search results returned in < 3 seconds |
| **Scalability** | Support 500K+ trials, 100K+ sites |
| **Availability** | 99% uptime for web application |
| **Data Freshness** | Trial data updated within 7 days of ClinicalTrials.gov |
| **Security** | No PII storage; standard web security practices |

### 4.3 Out of Scope (V1)

- Full CRO replacement functionality
- Enrollment prediction models
- Private/proprietary datasets
- Complex ML models (beyond heuristics)
- International regulatory compliance features
- Real-time trial monitoring

---

## 5. System Architecture

### 5.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER                               │
├─────────────────────────────────────────────────────────────────────┤
│  Web Application (React)                                             │
│  - Search Interface                                                  │
│  - Results Dashboard                                                 │
│  - Export Tools                                                      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           API LAYER                                  │
├─────────────────────────────────────────────────────────────────────┤
│  FastAPI Backend                                                     │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                  │
│  │ Search API  │  │ Query Parser│  │ Export API  │                  │
│  └─────────────┘  └─────────────┘  └─────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         SERVICE LAYER                                │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │
│  │ Query Parser    │  │ Scoring Engine  │  │ LLM Explanation │      │
│  │ (LLM-powered)   │  │ (Heuristics)    │  │ Generator       │      │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          DATA LAYER                                  │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │
│  │ PostgreSQL      │  │ Vector Store    │  │ Cache (Redis)   │      │
│  │ (Structured)    │  │ (Embeddings)    │  │                 │      │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                       DATA PIPELINE LAYER                            │
├─────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐      │
│  │ CT.gov Ingester │  │ Data Processor  │  │ Metrics         │      │
│  │                 │  │ & Normalizer    │  │ Calculator      │      │
│  └─────────────────┘  └─────────────────┘  └─────────────────┘      │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      EXTERNAL DATA SOURCES                           │
├─────────────────────────────────────────────────────────────────────┤
│  ClinicalTrials.gov API  │  (Future: PubMed, FDA, etc.)             │
└─────────────────────────────────────────────────────────────────────┘
```

### 5.2 Component Details

#### 5.2.1 Data Ingestion Pipeline

```
ClinicalTrials.gov API
        │
        ▼
┌───────────────────┐
│  Bulk Downloader  │  ← Initial backfill (~500K studies)
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  JSON Parser      │  ← Extract relevant fields
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  Data Normalizer  │  ← Standardize names, locations
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  PI-Site Linker   │  ← Heuristic matching
└───────────────────┘
        │
        ▼
┌───────────────────┐
│  Metrics Engine   │  ← Calculate performance scores
└───────────────────┘
        │
        ▼
    PostgreSQL
```

#### 5.2.2 Query Processing Flow

```
User Query: "Phase 2 lung cancer trial in US, need fast enrollment"
                            │
                            ▼
                ┌───────────────────────┐
                │   LLM Query Parser    │
                └───────────────────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │  Structured Query     │
                │  {                    │
                │    indication: "lung  │
                │      cancer",         │
                │    phase: "Phase 2",  │
                │    location: "US",    │
                │    priority: "fast    │
                │      enrollment"      │
                │  }                    │
                └───────────────────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │   Database Query      │
                │   + Filtering         │
                └───────────────────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │   Scoring Engine      │
                └───────────────────────┘
                            │
                            ▼
                ┌───────────────────────┐
                │   LLM Explanation     │
                └───────────────────────┘
                            │
                            ▼
                    Ranked Results
```

---

## 6. Data Model

### 6.1 Entity Relationship Diagram

```
┌─────────────────┐       ┌─────────────────┐       ┌─────────────────┐
│     trials      │       │   trial_sites   │       │     sites       │
├─────────────────┤       ├─────────────────┤       ├─────────────────┤
│ trial_id (PK)   │──────<│ trial_id (FK)   │>──────│ site_id (PK)    │
│ nct_id          │       │ site_id (FK)    │       │ name            │
│ title           │       │ pi_id (FK)      │       │ facility        │
│ condition       │       │ status          │       │ city            │
│ phase           │       │ enrollment_count│       │ state           │
│ status          │       └─────────────────┘       │ country         │
│ start_date      │               │                 │ institution_type│
│ completion_date │               │                 └─────────────────┘
│ enrollment      │               │
│ sponsor         │               ▼
└─────────────────┘       ┌─────────────────┐
                          │      pis        │
                          ├─────────────────┤
                          │ pi_id (PK)      │
                          │ name            │
                          │ affiliation     │
                          │ role            │
                          └─────────────────┘
                                  │
                                  ▼
                          ┌─────────────────┐
                          │  pi_metrics     │
                          ├─────────────────┤
                          │ pi_id (FK)      │
                          │ indication      │
                          │ total_trials    │
                          │ completed_trials│
                          │ completion_rate │
                          │ avg_duration    │
                          └─────────────────┘
```

### 6.2 Table Definitions

#### `trials`
```sql
CREATE TABLE trials (
    trial_id        SERIAL PRIMARY KEY,
    nct_id          VARCHAR(20) UNIQUE NOT NULL,
    title           TEXT,
    brief_summary   TEXT,
    condition       TEXT[],
    phase           VARCHAR(50),
    status          VARCHAR(50),
    start_date      DATE,
    completion_date DATE,
    enrollment      INTEGER,
    sponsor         VARCHAR(255),
    created_at      TIMESTAMP DEFAULT NOW(),
    updated_at      TIMESTAMP DEFAULT NOW()
);
```

#### `sites`
```sql
CREATE TABLE sites (
    site_id         SERIAL PRIMARY KEY,
    name            VARCHAR(500),
    facility        VARCHAR(500),
    city            VARCHAR(100),
    state           VARCHAR(100),
    country         VARCHAR(100),
    zip             VARCHAR(20),
    institution_type VARCHAR(50),  -- academic, community, etc.
    created_at      TIMESTAMP DEFAULT NOW()
);
```

#### `pis` (Principal Investigators)
```sql
CREATE TABLE pis (
    pi_id           SERIAL PRIMARY KEY,
    name            VARCHAR(255) NOT NULL,
    name_normalized VARCHAR(255),  -- for matching
    affiliation     VARCHAR(500),
    role            VARCHAR(100),  -- Principal Investigator, Study Director, etc.
    created_at      TIMESTAMP DEFAULT NOW()
);
```

#### `trial_sites` (Junction Table)
```sql
CREATE TABLE trial_sites (
    id              SERIAL PRIMARY KEY,
    trial_id        INTEGER REFERENCES trials(trial_id),
    site_id         INTEGER REFERENCES sites(site_id),
    pi_id           INTEGER REFERENCES pis(pi_id),
    status          VARCHAR(50),
    enrollment_count INTEGER,
    UNIQUE(trial_id, site_id, pi_id)
);
```

#### `pi_metrics` (Computed Metrics)
```sql
CREATE TABLE pi_metrics (
    id                  SERIAL PRIMARY KEY,
    pi_id               INTEGER REFERENCES pis(pi_id),
    site_id             INTEGER REFERENCES sites(site_id),
    indication          VARCHAR(255),
    total_trials        INTEGER DEFAULT 0,
    completed_trials    INTEGER DEFAULT 0,
    completion_rate     DECIMAL(5,4),
    avg_trial_duration  INTEGER,  -- days
    last_trial_date     DATE,
    updated_at          TIMESTAMP DEFAULT NOW(),
    UNIQUE(pi_id, site_id, indication)
);
```

### 6.3 Data Source Mapping

| ClinicalTrials.gov Field | Our Field |
|--------------------------|-----------|
| `protocolSection.identificationModule.nctId` | `trials.nct_id` |
| `protocolSection.identificationModule.officialTitle` | `trials.title` |
| `protocolSection.conditionsModule.conditions` | `trials.condition` |
| `protocolSection.designModule.phases` | `trials.phase` |
| `protocolSection.statusModule.overallStatus` | `trials.status` |
| `protocolSection.contactsLocationsModule.locations` | `sites.*` |
| `protocolSection.contactsLocationsModule.overallOfficials` | `pis.*` |

---

## 7. Core Algorithms

### 7.1 PI-Site Linking Algorithm

**Problem:** ClinicalTrials.gov provides `overallOfficials` (PIs) and `locations` (sites) separately, without explicit linkage.

**V1 Heuristic Approach:**

```python
def link_pi_to_site(pi: PI, sites: List[Site]) -> Optional[Site]:
    """
    Attempt to link a PI to a site using affiliation matching.
    """
    if not pi.affiliation:
        return None
    
    pi_affiliation_normalized = normalize_institution_name(pi.affiliation)
    
    best_match = None
    best_score = 0.0
    
    for site in sites:
        site_name_normalized = normalize_institution_name(site.name)
        
        # Fuzzy string matching
        score = fuzzy_match(pi_affiliation_normalized, site_name_normalized)
        
        if score > best_score and score > THRESHOLD:
            best_score = score
            best_match = site
    
    return best_match

def normalize_institution_name(name: str) -> str:
    """
    Normalize institution names for matching.
    - Remove common suffixes (Inc., LLC, etc.)
    - Standardize abbreviations (Univ -> University)
    - Lowercase
    """
    # Implementation details...
```

**Matching Confidence Levels:**
- **High (>0.9):** Direct name match
- **Medium (0.7-0.9):** Fuzzy match with common variations
- **Low (<0.7):** Uncertain, flag for review

### 7.2 Scoring Algorithm

```python
def calculate_pi_site_score(
    pi_site: PISitePair,
    query: StructuredQuery
) -> float:
    """
    Calculate recommendation score for a PI-site combination.
    
    Score = weighted sum of:
    - Indication experience (35%)
    - Total experience (25%)
    - Completion rate (20%)
    - Geographic match (20%)
    """
    
    weights = {
        'indication_experience': 0.35,
        'total_experience': 0.25,
        'completion_rate': 0.20,
        'geographic_match': 0.20
    }
    
    scores = {}
    
    # 1. Indication Experience (0-1)
    indication_trials = get_trials_for_indication(pi_site, query.indication)
    scores['indication_experience'] = min(indication_trials / 10, 1.0)
    
    # 2. Total Experience (0-1)
    total_trials = get_total_trials(pi_site)
    scores['total_experience'] = min(total_trials / 20, 1.0)
    
    # 3. Completion Rate (0-1)
    scores['completion_rate'] = pi_site.metrics.completion_rate or 0.5
    
    # 4. Geographic Match (0-1)
    scores['geographic_match'] = calculate_geo_match(pi_site.site, query.location)
    
    # Weighted sum
    final_score = sum(
        weights[k] * scores[k] for k in weights
    )
    
    return final_score
```

### 7.3 Query Parsing (LLM-Powered)

```python
QUERY_PARSE_PROMPT = """
Extract structured trial parameters from the following query.

Query: {user_query}

Return JSON with these fields:
- indication: the disease/condition (e.g., "lung cancer", "diabetes")
- phase: trial phase (e.g., "Phase 1", "Phase 2", "Phase 3")
- location: geographic preference (e.g., "United States", "Europe")
- priority: key priorities mentioned (e.g., "fast enrollment", "experienced sites")
- therapeutic_area: broader category (e.g., "oncology", "cardiology")

If a field is not mentioned, set it to null.
"""

async def parse_query(user_query: str) -> StructuredQuery:
    response = await llm.complete(
        QUERY_PARSE_PROMPT.format(user_query=user_query)
    )
    return StructuredQuery.parse_raw(response)
```

---

## 8. API Design

### 8.1 REST Endpoints

#### Search Endpoint
```
POST /api/v1/search
```

**Request:**
```json
{
  "query": "Phase 2 lung cancer trial in US, need fast enrollment",
  "filters": {
    "min_experience": 5,
    "institution_types": ["academic", "cancer_center"]
  },
  "limit": 10
}
```

**Response:**
```json
{
  "query_parsed": {
    "indication": "lung cancer",
    "phase": "Phase 2",
    "location": "United States",
    "priority": "fast enrollment"
  },
  "results": [
    {
      "rank": 1,
      "score": 0.89,
      "site": {
        "id": 1234,
        "name": "MD Anderson Cancer Center",
        "city": "Houston",
        "state": "TX",
        "country": "United States"
      },
      "pi": {
        "id": 5678,
        "name": "Dr. Jane Smith",
        "affiliation": "MD Anderson Cancer Center"
      },
      "metrics": {
        "indication_trials": 12,
        "total_trials": 45,
        "completion_rate": 0.92
      },
      "explanation": "Strong lung cancer experience with 12 prior trials. High completion rate (92%). Located in target geography."
    }
  ],
  "total_results": 156,
  "execution_time_ms": 234
}
```

#### Get Site Details
```
GET /api/v1/sites/{site_id}
```

#### Get PI Details
```
GET /api/v1/pis/{pi_id}
```

#### Export Results
```
POST /api/v1/export
```

### 8.2 API Error Handling

```json
{
  "error": {
    "code": "INVALID_QUERY",
    "message": "Could not parse trial parameters from query",
    "details": {
      "query": "...",
      "suggestion": "Please include indication and phase information"
    }
  }
}
```

---

## 9. Implementation Phases

### Phase 1: Foundation (Weeks 1-2)
**Goal:** Data pipeline and basic database

| Task | Duration | Deliverable |
|------|----------|-------------|
| Set up project structure | 1 day | Repository, CI/CD |
| Design and create database schema | 2 days | PostgreSQL tables |
| Build ClinicalTrials.gov API client | 2 days | Python client |
| Implement bulk data ingestion | 3 days | Backfill script |
| Parse and normalize trial data | 2 days | Data in DB |

**Exit Criteria:**
- [ ] 500K+ trials loaded into database
- [ ] Sites and PIs extracted and stored
- [ ] Basic data quality validation passing

### Phase 2: Core Logic (Weeks 3-4)
**Goal:** PI-site linking and scoring

| Task | Duration | Deliverable |
|------|----------|-------------|
| Implement PI-site linking heuristics | 3 days | Linking algorithm |
| Build metrics calculation pipeline | 2 days | Computed metrics |
| Implement scoring algorithm | 2 days | Scoring engine |
| Create search/filter logic | 2 days | Query engine |
| Unit tests for core logic | 1 day | Test suite |

**Exit Criteria:**
- [ ] PI-site pairs linked with confidence scores
- [ ] Metrics calculated for all PI-site pairs
- [ ] Scoring returns ranked results

### Phase 3: API & LLM Integration (Weeks 5-6)
**Goal:** Working API with natural language support

| Task | Duration | Deliverable |
|------|----------|-------------|
| Set up FastAPI application | 1 day | API skeleton |
| Implement search endpoint | 2 days | `/api/v1/search` |
| Integrate LLM for query parsing | 2 days | Query parser |
| Integrate LLM for explanations | 2 days | Explanation generator |
| API documentation | 1 day | OpenAPI spec |
| Integration tests | 2 days | Test suite |

**Exit Criteria:**
- [ ] API accepts natural language queries
- [ ] Returns ranked, explained results
- [ ] API documentation complete

### Phase 4: Frontend MVP (Weeks 7-8)
**Goal:** Usable web interface

| Task | Duration | Deliverable |
|------|----------|-------------|
| Set up React application | 1 day | Frontend skeleton |
| Build search interface | 3 days | Search page |
| Build results display | 3 days | Results component |
| Implement filters | 2 days | Filter UI |
| Export functionality | 1 day | CSV/PDF export |

**Exit Criteria:**
- [ ] Users can search via web UI
- [ ] Results displayed with explanations
- [ ] Export working

### Phase 5: Polish & Launch (Weeks 9-10)
**Goal:** Production-ready MVP

| Task | Duration | Deliverable |
|------|----------|-------------|
| Performance optimization | 2 days | <3s response time |
| Error handling & edge cases | 2 days | Robust system |
| Deployment setup | 2 days | Production environment |
| User testing & feedback | 2 days | Feedback incorporated |
| Documentation | 2 days | User guide |

**Exit Criteria:**
- [ ] System deployed and accessible
- [ ] Performance targets met
- [ ] Initial users onboarded

---

## 10. Technical Stack

### Backend
| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Language** | Python 3.11+ | Data processing, ML ecosystem |
| **API Framework** | FastAPI | Async, auto-docs, type hints |
| **Database** | PostgreSQL | Relational data, full-text search |
| **Cache** | Redis | Query caching, rate limiting |
| **Task Queue** | Celery | Background data processing |

### Frontend
| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Framework** | React 18 | Component-based, ecosystem |
| **Styling** | TailwindCSS | Rapid UI development |
| **Components** | shadcn/ui | Modern, accessible components |
| **State** | React Query | Server state management |

### Infrastructure
| Component | Technology | Rationale |
|-----------|------------|-----------|
| **Hosting** | AWS / Railway | Scalable, managed |
| **CI/CD** | GitHub Actions | Integrated with repo |
| **Monitoring** | Sentry | Error tracking |

### AI/ML
| Component | Technology | Rationale |
|-----------|------------|-----------|
| **LLM** | OpenAI GPT-4 / Claude | Query parsing, explanations |
| **Embeddings** | OpenAI / Sentence Transformers | Semantic search (future) |

---

## 11. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| **PI-site linking accuracy** | High | High | Start with high-confidence matches only; flag uncertain links |
| **Data incompleteness** | High | Medium | Be transparent about coverage; show confidence scores |
| **ClinicalTrials.gov API changes** | Medium | High | Abstract API layer; monitor for changes |
| **LLM costs** | Medium | Medium | Cache common queries; use smaller models where possible |
| **User adoption** | Medium | High | Focus on clear value prop; get early user feedback |
| **Regulatory concerns** | Low | High | Clearly state tool is for research/planning only |

---

## 12. Success Metrics

### MVP Success Criteria
| Metric | Target |
|--------|--------|
| **Data Coverage** | 80%+ of Phase 2-3 US trials have PI-site pairs |
| **Query Success Rate** | 90%+ of queries return relevant results |
| **Response Time** | <3 seconds for search queries |
| **User Satisfaction** | "Saved me 5+ hours of research" feedback |

### Growth Metrics (Post-MVP)
| Metric | Target |
|--------|--------|
| Weekly Active Users | 50+ in first 3 months |
| Queries per User | 5+ per session |
| Return Rate | 40%+ users return within 30 days |

---

## 13. Future Roadmap

### V1.1 - Enhanced Data (Month 3-4)
- PubMed integration for PI publication history
- FDA approval data for success signals
- Improved PI-site linking with ML

### V1.2 - Advanced Features (Month 5-6)
- Semantic search using embeddings
- Trial similarity matching
- Saved searches and alerts

### V2.0 - Knowledge Graph (Month 7-12)
- Build knowledge graph (People, Organizations, Science)
- Network analysis (PI collaborations, site relationships)
- Predictive enrollment modeling

### V3.0 - Agentic Capabilities (Year 2)
- Automated trial protocol writing assistance
- Inclusion/exclusion criteria optimization
- Regulatory filing automation
- International site expansion

---

## Appendix A: ClinicalTrials.gov API Reference

### Base URL
```
https://clinicaltrials.gov/api/v2/studies
```

### Key Endpoints
- `GET /studies` - Search studies
- `GET /studies/{nctId}` - Get single study

### Relevant Fields
```json
{
  "protocolSection": {
    "identificationModule": {
      "nctId": "NCT12345678",
      "officialTitle": "..."
    },
    "statusModule": {
      "overallStatus": "Completed"
    },
    "conditionsModule": {
      "conditions": ["Lung Cancer"]
    },
    "designModule": {
      "phases": ["Phase 2"]
    },
    "contactsLocationsModule": {
      "overallOfficials": [
        {
          "name": "John Smith, MD",
          "role": "Principal Investigator",
          "affiliation": "MD Anderson Cancer Center"
        }
      ],
      "locations": [
        {
          "facility": "MD Anderson Cancer Center",
          "city": "Houston",
          "state": "Texas",
          "country": "United States"
        }
      ]
    }
  }
}
```

---

## Appendix B: Sample Queries

### Query 1: Oncology Trial
**Input:** "Phase 2 lung cancer trial in US, need fast enrollment"

**Parsed:**
```json
{
  "indication": "lung cancer",
  "phase": "Phase 2",
  "location": "United States",
  "priority": "fast enrollment"
}
```

### Query 2: Rare Disease
**Input:** "Looking for sites experienced in Duchenne muscular dystrophy, Phase 1/2, preferably academic centers"

**Parsed:**
```json
{
  "indication": "Duchenne muscular dystrophy",
  "phase": "Phase 1/2",
  "location": null,
  "priority": "experienced sites",
  "institution_type": "academic"
}
```

---

*Document maintained by: [Team]*  
*Last updated: April 2026*
