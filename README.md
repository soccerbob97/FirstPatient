# FirstPatient

AI-powered system that recommends optimal PI + clinical trial site combinations for biotech sponsors.

## Features

- **Hybrid Search**: Combines semantic vector search with heuristic scoring
- **PI-Site Linking**: Infers relationships between investigators and sites using multiple strategies
- **Performance Metrics**: Tracks completion rates, trial counts, and experience by indication
- **Semantic Search**: Find PIs by expertise using natural language queries
- **Conversational Interface**: ChatGPT-style UI for natural language trial queries

## Current Status

| Component | Status |
|-----------|--------|
| Data ingestion (1000 trials) | ✅ Complete |
| PI-Site linking (3 strategies) | ✅ Complete |
| Vector embeddings (trials + PIs) | ✅ Complete |
| Hybrid recommendation engine | ✅ Complete |
| FastAPI backend | 🚧 In Progress |
| React frontend | 🚧 In Progress |

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
FirstPatient/
├── api/                          # FastAPI backend
│   ├── main.py                   # App entry point
│   ├── routes/
│   │   ├── recommendations.py    # POST /api/recommendations
│   │   ├── trials.py             # GET /api/trials
│   │   └── investigators.py      # GET /api/investigators
│   └── schemas.py                # Pydantic models
├── web/                          # React frontend
│   ├── src/
│   │   ├── components/           # UI components
│   │   ├── pages/                # Page views
│   │   └── api/                  # API client
│   ├── package.json
│   └── tailwind.config.js
├── src/                          # Core Python logic
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
├── supabase/
│   └── migrations/
│       ├── 001_initial_schema.sql
│       ├── 002_add_embeddings.sql
│       ├── 003_drop_raw_json.sql
│       └── 004_fix_recommendation_function.sql
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

| Layer | Technology |
|-------|------------|
| **Database** | Supabase (PostgreSQL + pgvector) |
| **Embeddings** | OpenAI text-embedding-3-small (1536 dim) |
| **Backend** | FastAPI + Uvicorn |
| **Frontend** | React 18 + Vite + TypeScript |
| **Styling** | TailwindCSS |
| **Data Source** | ClinicalTrials.gov API v2 |

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/recommendations` | Get PI+Site recommendations for a query |
| `GET` | `/api/trials` | List/search trials |
| `GET` | `/api/trials/{nct_id}` | Get trial details |
| `GET` | `/api/investigators` | Search investigators |

## UI Design

**Design Philosophy:**
- Clean, professional white & blue color scheme
- ChatGPT-inspired conversational layout
- No AI-generated icons/images
- Lucide React for minimal, consistent icons

**Color Palette:**
- Background: White (`#FFFFFF`)
- Sidebar: Light gray (`#F8FAFC`)
- Primary accent: Blue (`#2563EB`)
- Text: Dark gray (`#1E293B`)

**Layout:**
- Left sidebar: Search history, navigation
- Main area: Search input, results
- Result cards: PI name, site, location, score breakdown

## Future Ideas

- **Enrollment speed prediction**: Estimate time to hit enrollment targets
- **Sponsor matching**: Factor in prior work with similar sponsors
- **Geographic optimization**: Multi-site trial planning
- **Real-time updates**: Sync with ClinicalTrials.gov changes
- **Conversation history**: Save and revisit past searches
- **PI profiles**: Detailed view of investigator experience
