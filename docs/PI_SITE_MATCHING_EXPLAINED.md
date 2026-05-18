# How FirstPatient Matches PIs and Sites to Your Protocol

**Purpose**: Explain our intelligent matching approach for the tech demo  
**Audience**: Sponsors, CROs, investors  
**Tone**: Confident, technical but accessible

---

## Overview

FirstPatient uses **semantic vector search** combined with **multi-factor scoring** to find the best PI-site pairs for your specific protocol. This isn't keyword matching — it's AI-powered understanding of what makes a protocol unique and which investigators have the right experience to execute it.

---

## How It Works

### Step 1: Protocol Understanding

When you input a protocol (PDF or structured data), we extract:
- **Indication/Disease area** (e.g., EGFR-mutant NSCLC)
- **Phase** (Phase 1, 2, 3)
- **Intervention type** (small molecule, immunotherapy, cell therapy)
- **Operational requirements** (biopsies, imaging, PK sampling)
- **Eligibility complexity** (biomarker requirements, prior therapy lines)

This creates a **protocol fingerprint** — a structured representation of what makes your trial operationally unique.

---

### Step 2: Vector Embedding & Semantic Search

We convert your protocol into a **high-dimensional vector** using state-of-the-art embedding models. This vector captures the semantic meaning of your trial — not just keywords, but concepts.

```
Your Protocol → Vector Embedding (1024 dimensions)
                     ↓
         Compare against 394K+ trial embeddings
                     ↓
         Find trials with similar characteristics
                     ↓
         Identify PIs who ran those trials
```

**Why vectors?**
- Traditional keyword search: "NSCLC" matches "NSCLC" but misses "non-small cell lung cancer"
- Vector search: Understands that "EGFR-mutant NSCLC" is semantically similar to "EGFR+ lung adenocarcinoma"

---

### Step 3: Multi-Factor Execution Scoring

Raw semantic similarity isn't enough. A PI might have run trials with similar drug names but zero experience in your disease area. We layer multiple scoring factors:

| Factor | What It Measures | Weight |
|--------|------------------|--------|
| **Semantic Similarity** | How similar is the PI's trial history to your protocol? | 35% |
| **Disease Area Match** | What % of the PI's trials are in your indication? | 20% |
| **Phase Experience** | Has the PI run trials in your target phase? | 10% |
| **Trial Volume** | How many relevant trials has the PI completed? | 15% |
| **Completion Rate** | What's the PI's historical success rate? | 5% |
| **Role Confidence** | Was the PI a lead investigator or sub-I? | 15% |

**Result**: An **Execution Fit Score** that predicts how well this PI-site pair can execute YOUR specific protocol.

---

### Step 4: Enriched Data for Better Matching

We enrich our trial and investigator data from multiple sources:

| Data Source | What We Get | How It Helps |
|-------------|-------------|--------------|
| **ClinicalTrials.gov** | 394K+ trials, PI-site relationships | Foundation of trial history |
| **OpenAlex** | h-index, publications, affiliations | Academic reputation scoring |
| **openFDA** | Drug mechanism of action, drug class | Match by pharmacology, not just drug name |
| **PubMed** | Publication links to trials | Recover PI data from published results |

This enrichment means we can match on **mechanism of action** (e.g., "GLP-1 agonist") not just brand names, and we can assess PI reputation through academic metrics.

---

## What Makes Our Matching Different

### Protocol-First, Not Database-First

| Traditional Approach | FirstPatient Approach |
|---------------------|----------------------|
| Search: "Oncology" | Parse your protocol |
| Filter: "NSCLC" | Extract: EGFR-mutant, Phase 2, mandatory biopsy |
| Sort by: Trial count | Score: Execution fit per PI |
| Result: 500 oncologists | Result: 15 ranked PI-site pairs |

### Execution Fit, Not Just Experience

We don't just count trials. We score:
- **Relevance**: Has this PI done trials LIKE yours?
- **Capability**: Does the site have the required infrastructure?
- **Track Record**: What's the PI's completion rate?

### Transparent Reasoning

Every recommendation shows WHY the PI is a match:
- ✅ 12 trials in EGFR-mutant NSCLC
- ✅ Phase 2 experience (8 trials)
- ✅ Site has molecular testing capability
- ✅ 87% historical completion rate

---

## The Matching Pipeline

```
┌─────────────────────────────────────────────────────────────────┐
│                    PI/SITE MATCHING PIPELINE                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│  │   PROTOCOL   │────▶│   VECTOR     │────▶│   CANDIDATE  │    │
│  │   INPUT      │     │   SEARCH     │     │   RETRIEVAL  │    │
│  │              │     │              │     │              │    │
│  │ • PDF/Text   │     │ • Embed      │     │ • Top 100    │    │
│  │ • Structured │     │   protocol   │     │   similar    │    │
│  │   form       │     │ • Compare to │     │   trials     │    │
│  │              │     │   394K trials│     │ • Extract    │    │
│  │              │     │              │     │   PIs/sites  │    │
│  └──────────────┘     └──────────────┘     └──────────────┘    │
│                                                    │            │
│                                                    ▼            │
│  ┌──────────────┐     ┌──────────────┐     ┌──────────────┐    │
│  │   RANKED     │◀────│   EXECUTION  │◀────│   MULTI-     │    │
│  │   RESULTS    │     │   FIT SCORE  │     │   FACTOR     │    │
│  │              │     │              │     │   SCORING    │    │
│  │ • Top 15     │     │ • Weighted   │     │ • Disease    │    │
│  │   PI-site    │     │   composite  │     │   match      │    │
│  │   pairs      │     │ • 0-100%     │     │ • Phase exp  │    │
│  │ • Match      │     │              │     │ • Volume     │    │
│  │   reasons    │     │              │     │ • Completion │    │
│  └──────────────┘     └──────────────┘     └──────────────┘    │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## Technical Details (For Technical Audiences)

### Embedding Model
- **Model**: Voyage-3.5-lite (1024 dimensions)
- **Why**: +6.34% better retrieval quality than OpenAI text-embedding-3-small at same cost
- **Index**: HNSW (Hierarchical Navigable Small World) for fast approximate nearest neighbor search

### Embedding Content
Each trial embedding includes:
- Trial title and summary
- Conditions/indications
- Phase
- Intervention names
- Mechanism of action (from openFDA)
- Drug class
- Lead PI name

### Scoring Formula
```python
execution_fit = (
    0.35 * semantic_similarity +      # Vector cosine similarity
    0.20 * disease_area_match +       # % of PI trials in indication
    0.10 * phase_experience_match +   # Binary/graded phase match
    0.15 * experience_score +         # Normalized trial count
    0.05 * completion_rate +          # Historical success rate
    0.15 * role_confidence            # Lead PI vs sub-I
)
```

### Data Scale
- **Trials**: 394,214 (after cleanup)
- **Investigators**: 12,727 enriched with academic metrics
- **Embeddings**: 1024-dimensional vectors for all trials

---

## Demo Talking Points

When explaining matching in the demo:

> "We use vector embeddings to understand the semantic meaning of your protocol — not just keywords, but concepts. Then we layer in disease-area matching, phase experience, and completion rates to calculate an Execution Fit Score. The result: ranked recommendations of who can actually execute YOUR specific trial."

> "This isn't a database search. It's AI-powered matching that understands a Phase 2 EGFR-mutant NSCLC trial with mandatory biopsies is very different from a Phase 3 broad NSCLC trial — and finds PIs with the right experience for YOUR protocol."

---

## FAQ

**Q: How is this different from Citeline?**
> Citeline is a database — you search and filter. We score execution fit. We don't just find oncologists; we find oncologists who've run trials LIKE yours.

**Q: What if a PI doesn't have trials in our exact indication?**
> Our semantic matching finds related experience. A PI with extensive EGFR-mutant lung cancer experience will score well for an EGFR-mutant NSCLC trial, even if the exact terms differ.

**Q: How do you handle new drugs with no trial history?**
> We match on mechanism of action and drug class, not just drug names. A new GLP-1 agonist will match PIs who've run other GLP-1 trials.

**Q: What about site capabilities?**
> We derive site requirements from the protocol (e.g., "needs IR for biopsies") and match against site profiles. Sites without required capabilities are deprioritized.

---

*Last updated: May 17, 2026*
