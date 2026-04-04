# Clinical Trial Site Recommender

AI-powered system that recommends optimal PI + clinical trial site combinations for biotech sponsors.

## Features

- **Hybrid Search**: Combines semantic vector search with heuristic scoring
- **PI-Site Linking**: Infers relationships between investigators and sites using multiple strategies
- **Performance Metrics**: Tracks completion rates, trial counts, and experience by indication
- **Semantic Search**: Find PIs by expertise using natural language queries

## Architecture

```
User Query: "Phase 2 breast cancer trial in California"
                    │
                    ▼
┌─────────────────────────────────────────────────────┐
│  1. VECTOR SEARCH (Semantic Relevance)              │
│     Embed query → Find similar trials via pgvector  │
└─────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────┐
│  2. HEURISTIC SCORING (Performance Ranking)         │
│     0.40 * semantic_similarity                      │
│     0.25 * experience (trial count)                 │
│     0.20 * completion_rate                          │
│     0.15 * link_confidence (site_contact > oversight)│
└─────────────────────────────────────────────────────┘
                    │
                    ▼
┌─────────────────────────────────────────────────────┐
│  3. RETURN: Ranked PI + Site recommendations        │
└─────────────────────────────────────────────────────┘
```

## Quick Start

### 1. Set up Supabase

1. Create a new project at [supabase.com](https://supabase.com)
2. Go to **SQL Editor** and run the migrations:
   ```sql
   -- Run in order:
   supabase/migrations/001_initial_schema.sql
   supabase/migrations/002_add_embeddings.sql
   ```
3. Get your API keys from **Settings → API Keys**

### 2. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your credentials:
```
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_KEY=sb_publishable_...
SUPABASE_SERVICE_KEY=sb_secret_...
OPENAI_API_KEY=sk-...
```

### 3. Install Dependencies

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

### 4. Download Data from ClinicalTrials.gov

1. Go to https://clinicaltrials.gov/search
2. Click **Download** button
3. Select:
   - **File Format:** JSON
   - **Results to Download:** Top 1000 (for testing) or All studies
   - **Data Fields:** All available
4. Save to project folder

### 5. Load Data and Generate Embeddings

```bash
# Load trials into database
python -m src.ingestion.bulk_loader ctg-studies.json

# Generate embeddings for semantic search
python scripts/generate_embeddings.py
```

### 6. Get Recommendations

```python
from src.recommendations.recommender import get_recommendations

results = get_recommendations(
    query="Phase 2 oncology trial for breast cancer",
    country="United States",
    max_results=10
)

for r in results:
    print(f"{r['investigator']['name']} at {r['site']['name']}")
    print(f"  Score: {r['scores']['final']}")
```

## Project Structure

```
ClinicalTrialProject/
├── docs/
│   └── DESIGN_DOCUMENT.md        # Full system design
├── supabase/
│   └── migrations/
│       ├── 001_initial_schema.sql
│       └── 002_add_embeddings.sql
├── src/
│   ├── config.py                 # Configuration
│   ├── db/
│   │   └── supabase_client.py
│   ├── ingestion/
│   │   ├── parser.py             # Parse CT.gov responses
│   │   ├── loader.py             # Load into Supabase
│   │   └── bulk_loader.py        # Bulk JSON loader
│   ├── embeddings/
│   │   └── generator.py          # OpenAI embedding generation
│   └── recommendations/
│       └── recommender.py        # Hybrid search engine
├── scripts/
│   ├── generate_embeddings.py    # Generate embeddings for DB
│   └── analyze_data_structure.py # Data analysis utilities
├── requirements.txt
└── .env
```

## Database Schema

### Core Tables

| Table | Description |
|-------|-------------|
| `trials` | Clinical trial metadata + embedding vector |
| `sites` | Trial locations/facilities |
| `investigators` | PIs and study officials + expertise embedding |

### Relationship Tables

| Table | Description |
|-------|-------------|
| `trial_sites` | Trial ↔ Site relationships |
| `trial_investigators` | Trial ↔ Investigator relationships |
| `investigator_sites` | PI ↔ Site links with `link_type` |

### PI-Site Link Types

| link_type | Meaning | Confidence |
|-----------|---------|------------|
| `site_contact` | Explicitly listed in location.contacts | High |
| `affiliation_match` | PI's affiliation matches site name | Medium |
| `oversight` | Overall official with study-level oversight | Lower |

### Metrics Tables

| Table | Description |
|-------|-------------|
| `investigator_metrics` | PI performance by indication |
| `site_metrics` | Site performance by indication |

## Tech Stack

- **Database**: Supabase (PostgreSQL + pgvector)
- **Embeddings**: OpenAI text-embedding-3-small (1536 dimensions)
- **Data Source**: ClinicalTrials.gov API v2
- **Language**: Python 3.11+

## Development Status

- [x] Data ingestion pipeline
- [x] PI-Site linking (3 strategies)
- [x] Vector embeddings schema
- [x] Hybrid recommendation engine
- [ ] Metrics computation
- [ ] API endpoints
- [ ] Frontend UI

## Future Ideas

- **Enrollment speed prediction**: Estimate time to hit enrollment targets
- **Sponsor matching**: Factor in prior work with similar sponsors
- **Geographic optimization**: Multi-site trial planning
- **Real-time updates**: Sync with ClinicalTrials.gov changes
- **LLM-powered insights**: Natural language trial summaries
