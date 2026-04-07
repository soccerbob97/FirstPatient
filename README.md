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
| Data ingestion (577K trials) | ✅ Complete |
| PI-Site linking (3 strategies) | ✅ Complete |
| Vector embeddings (577K trials) | ✅ Complete |
| HNSW index (43K demo subset) | ✅ Complete |
| Hybrid recommendation engine | ✅ Complete |
| FastAPI backend | ✅ Complete |
| React frontend (Chat UI) | ✅ Complete |
| User authentication | ✅ Complete |

## Vector Search & HNSW Index

### Current Setup (Demo Mode)

Due to Supabase Pro plan memory limitations, we use a **demo subset** for fast vector search:

| Item | Value |
|------|-------|
| **Demo table** | `trial_embeddings_demo` |
| **Indexed trials** | 43,080 (breast cancer, obesity, diabetes) |
| **HNSW index size** | 337 MB |
| **Search function** | `search_trials_by_embedding()` |

The demo covers common therapeutic areas and provides sub-second search performance.

### Why Not Full Index?

Building an HNSW index on all 577K trials requires:
- ~500MB - 1GB `maintenance_work_mem` for efficient build
- Supabase Pro shared memory limit is ~128MB
- Index build with 128MB spills to disk constantly and fails

**Full embeddings exist** in the `trials.embedding` column (577K vectors), but the HNSW index only covers the demo subset.

### To Build Full Index (Future)

Options to index all 577K trials:
1. **Upgrade Supabase compute** - Larger instance = more shared memory
2. **Use dedicated Postgres** - Full control over `maintenance_work_mem`
3. **Use Supabase branching** - Build index on branch, then merge

### Memory Calculation

For 550K vectors × 1536 dimensions:
- Raw vector data: ~3.4 GB
- HNSW graph overhead (m=16): ~140 MB  
- Efficient build memory: 500MB - 1GB

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

## Roadmap: Conversational Chat Feature

### Overview

Transform the search interface into a conversational assistant that guides users through PI+Site discovery. The chatbot will have database access to answer follow-up questions about recommendations.

### Example Flow

```
User: "Phase 2 diabetes trial in the United States"

→ System fetches recommendations, displays PI+Site cards

Assistant: "I found 10 PI+Site recommendations for Phase 2 diabetes trials 
in the US. The top match is Dr. Smith at Mount Sinai with a 56% relevance 
score and 12 completed trials in metabolic disorders."

User: "Tell me more about Dr. Smith's experience with diabetes trials"

→ System queries database for Dr. Smith's trial history

Assistant: "Dr. Smith has been involved in 8 diabetes-related trials over 
the past 5 years, including 3 Phase 2 studies. Their completion rate is 87%, 
and they've worked with Novo Nordisk and Eli Lilly."

User: "Which sites have the highest completion rates?"

→ System analyzes recommendation data

Assistant: "Among your recommendations, the top 3 sites by completion rate are:
1. Mayo Clinic (94%) - Dr. Johnson
2. Cleveland Clinic (91%) - Dr. Williams  
3. Mount Sinai (87%) - Dr. Smith"

User: "Compare Mount Sinai vs Mayo Clinic for this trial"

→ System queries both sites' metrics

Assistant: "Here's a comparison..."
```

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    FRONTEND (React)                         │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Conversation UI (message bubbles)                   │   │
│  │  - User messages (right-aligned)                     │   │
│  │  - Assistant messages (left-aligned)                 │   │
│  │  - Recommendation cards (inline)                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    BACKEND (FastAPI)                        │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────┐  │
│  │ /api/chat    │  │ /api/recs    │  │ Tool Functions   │  │
│  │              │  │              │  │ - query_trials   │  │
│  │ Orchestrates │  │ Hybrid       │  │ - get_pi_details │  │
│  │ conversation │  │ recommender  │  │ - compare_sites  │  │
│  └──────────────┘  └──────────────┘  └──────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    LLM (Model-Agnostic)                     │
│  - OpenAI GPT-4 / GPT-3.5                                   │
│  - Anthropic Claude                                         │
│  - Local models via OpenAI-compatible API                   │
│  - Function calling for database queries                    │
└─────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    DATABASE (Supabase)                      │
│  - conversations (chat history)                             │
│  - messages (individual messages)                           │
│  - trials, investigators, sites (existing)                  │
└─────────────────────────────────────────────────────────────┘
```

### Implementation Plan

#### Phase 1: Database Schema
- [ ] Create `conversations` table (id, user_id, title, created_at)
- [ ] Create `messages` table (id, conversation_id, role, content, metadata)
- [ ] Add indexes for efficient retrieval

#### Phase 2: Backend Chat Endpoint
- [ ] Create `POST /api/chat` endpoint
- [ ] Implement model-agnostic LLM client (OpenAI SDK compatible)
- [ ] Define tool functions for database queries:
  - `get_recommendations` - trigger hybrid search
  - `get_investigator_details` - fetch PI info
  - `get_site_details` - fetch site info  
  - `compare_options` - side-by-side comparison
  - `query_trials` - search trial history
- [ ] System prompt with context about recommendations

#### Phase 3: Frontend Conversation UI
- [ ] Convert results view to message bubbles
- [ ] User messages right-aligned, assistant left-aligned
- [ ] Recommendation cards rendered inline in conversation
- [ ] Typing indicator during LLM response
- [ ] "New Chat" button resets conversation

#### Phase 4: Persistence & History
- [ ] Save conversations to database
- [ ] Load conversation history in sidebar
- [ ] Resume previous conversations

### Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|  
| LLM Integration | OpenAI SDK | Model-agnostic, supports GPT, Claude, local models |
| Function Calling | OpenAI tools format | Standard format, works across providers |
| Message Storage | Supabase | Already using for data, real-time subscriptions |
| Streaming | SSE | Real-time token streaming for better UX |

## Future Ideas

- **Enrollment speed prediction**: Estimate time to hit enrollment targets
- **Sponsor matching**: Factor in prior work with similar sponsors
- **Geographic optimization**: Multi-site trial planning
- **Real-time updates**: Sync with ClinicalTrials.gov changes
- **PI profiles**: Detailed view of investigator experience
- **Export**: Download recommendations as PDF/CSV
