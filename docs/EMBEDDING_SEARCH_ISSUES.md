# Embedding Search Issues & Improvement Plan

**Date**: May 15, 2026  
**Status**: Temporary workarounds in place; long-term fix required  
**Related doc**: [PROD_ACTION_ITEMS_PLAN.md](./PROD_ACTION_ITEMS_PLAN.md) — Action Item 2 (Improved Embeddings) and Action Item 3 (Data-Driven Scoring)

---

## Problem Statement

The current embedding search matches trials based on **overall text similarity**, which causes drug names and trial design language to dominate over disease area relevance. This leads to:

1. **False positives** — PIs with no disease-area experience ranking at the top
2. **Missing experts** — PIs with deep disease-area expertise not appearing in results
3. **No phase matching** — Phase 1 PIs recommended for Phase 2/3 studies

---

## Case Study: Colorectal Cancer Query

**Query**: "A Phase II, Open-label, Multicenter Study of PM060184 in Patients with Advanced Colorectal Cancer after Standard Treatment"

### What happened

| PI | Rank | Score | CRC Trials | Phase 2+ Trials | Issue |
|----|------|-------|------------|-----------------|-------|
| **Mark Ratain** | #1 | 95% | 0 | 0 | False positive — matched on PM-series drug name |
| **Josep Tabernero** | #2 | 91% | 5+ | Yes | Good match, but was Study Chair on this exact trial |
| **Norman Wolmark** | Not shown | — | 16 | Yes | Missing — best CRC PI in database |
| **Leonard B. Saltz** | Not shown | — | 8 | Yes | Missing — Memorial Sloan Kettering CRC expert |
| **Marwan Fakih** | Not shown | — | 7 | Yes | Missing — City of Hope CRC expert |

### Root Cause Analysis

**Why Mark Ratain ranked #1 (false positive):**
- His trials include PM02734 and PM01183 (same PM-series drug family as PM060184)
- Embedding similarity is driven by "Phase I...Open-label...PM0xxxx...Advanced Solid Tumors"
- The embedding matched on **drug name pattern + trial design language**, not disease area
- His 7 trials are ALL Phase 1, NONE are colorectal

**Why Norman Wolmark didn't appear (false negative):**
- His 16 colorectal trials use drugs like cetuximab, oxaliplatin, bevacizumab — different drug families
- Trial titles like "Combination Chemotherapy...Colorectal Cancer With Liver Metastases" don't match "PM060184"
- Embedding similarity to the query is below the 0.5 threshold (top results range: 0.689–0.797)
- The search only returns 50 trials; none of Wolmark's are in that top 50

### Conclusion

The embedding search optimizes for **trial-to-trial similarity** (same drug, same design), not for **PI disease-area expertise**. This is fundamentally the wrong objective for PI recommendation.

---

## Temporary Workarounds (Demo)

### 1. Mark Ratain — avoid_search on PM-series trials

Set `avoid_search = true` on 2 trials that caused false match:

| Trial ID | NCT ID | Title |
|----------|--------|-------|
| 299985 | NCT00404521 | A Phase I Study of **PM02734** in Subjects With Advanced Malignant Solid Tumors |
| 574420 | NCT00877474 | Phase I...Clinical and Pharmacokinetic Study of **PM01183** in Patients With Advanced Solid Tumors |

**TODO: Revert these once long-term fix is in place.** SQL to restore:
```sql
UPDATE trials SET avoid_search = false WHERE id IN (299985, 574420);
```

### 2. Generic name filtering

Added filters for non-PI names (generic roles, sponsor names, placeholders) in `recommender.py`.

---

## Long-Term Solutions

### Solution 1: Disease-Area Matching (High Priority)

Extract conditions/disease from the user query and add a **condition overlap score** to the ranking.

**How it works:**
1. Parse query to extract disease keywords (e.g., "colorectal cancer")
2. For each candidate PI, count what % of their trials involve that condition
3. Add `condition_overlap` as a scoring component (weight: 0.15–0.20)

```python
def get_condition_overlap(investigator_id: int, query_conditions: list[str]) -> float:
    """
    Calculate what fraction of a PI's trials match the query conditions.
    Returns 0.0-1.0
    """
    # Get all conditions from PI's trials
    pi_conditions = get_pi_trial_conditions(investigator_id)
    
    # Fuzzy match query conditions against PI's conditions
    matches = sum(1 for c in pi_conditions if any(
        query_cond.lower() in c.lower() for query_cond in query_conditions
    ))
    
    return min(matches / max(len(pi_conditions), 1), 1.0)
```

**Impact**: Norman Wolmark (16/54 trials = 30% CRC) would score much higher than Mark Ratain (0% CRC).

### Solution 2: Phase Matching (Medium Priority)

Add a binary or graded score for phase experience match.

```python
def get_phase_match(investigator_id: int, query_phase: str) -> float:
    """
    Score based on PI's experience in the target phase.
    """
    pi_phases = get_pi_trial_phases(investigator_id)
    
    if query_phase in pi_phases:
        return 1.0  # Direct match
    
    # Adjacent phase gets partial credit
    adjacent = {
        "PHASE1": ["PHASE1, PHASE2"],
        "PHASE2": ["PHASE1, PHASE2", "PHASE2, PHASE3"],
        "PHASE3": ["PHASE2, PHASE3"],
    }
    if any(p in pi_phases for p in adjacent.get(query_phase, [])):
        return 0.7
    
    return 0.3  # No phase match
```

**Impact**: Mark Ratain (all Phase 1) would be penalized for a Phase 2 query.

### Solution 3: Two-Pass Search (High Priority)

Instead of relying solely on embedding similarity, use two parallel search strategies:

```
Pass 1: Embedding similarity (current approach)
  → Finds trials with similar design/drug/language
  → Good for: same drug family, similar trial designs

Pass 2: Condition-based search
  → Find trials matching the disease area
  → Find PIs on those trials
  → Good for: disease-area expertise

Combined: Merge and re-rank using weighted score
```

This ensures disease-area experts always appear, even if their trial titles don't match the drug name.

### Solution 4: Enriched Embeddings (Long-Term)

As documented in [PROD_ACTION_ITEMS_PLAN.md](./PROD_ACTION_ITEMS_PLAN.md) Action Item 2:

Current embedding text only includes:
- Trial title
- Brief summary
- Conditions

Planned embedding text will include:
- ✅ Conditions (weighted more heavily)
- ✅ Phase
- ✅ Intervention names
- ✅ Mechanism of action (from openFDA)
- ✅ Drug class
- ✅ Lead PI name

This should improve disease-area matching within the embedding itself.

---

## Updated Scoring Weights (Proposed)

### Current (problematic)
```python
weights = {
    "similarity": 0.60,       # Embedding similarity (drug name dominates)
    "experience": 0.15,       # Trial count
    "completion": 0.10,       # Completion rate
    "link_confidence": 0.15,  # Role confidence
}
```

### Proposed (with disease + phase matching)
```python
weights = {
    "similarity": 0.35,         # Embedding similarity (reduced)
    "condition_overlap": 0.20,  # NEW: Disease area match
    "phase_match": 0.10,        # NEW: Phase experience match
    "experience": 0.15,         # Trial count
    "completion": 0.05,         # Completion rate
    "link_confidence": 0.15,    # Role confidence
}
```

---

## Implementation Priority

| # | Solution | Effort | Impact | Dependency |
|---|----------|--------|--------|------------|
| 1 | **Condition-based matching** | 2-3 hours | High | None |
| 2 | **Phase matching** | 1-2 hours | Medium | None |
| 3 | **Two-pass search** | 4-6 hours | High | Solution 1 |
| 4 | **Enriched embeddings** | 8-12 hours | High | OpenAlex enrichment, openFDA enrichment |

Solutions 1 and 2 can be implemented immediately without any data pipeline changes. Solution 3 builds on them. Solution 4 is the long-term fix that requires completing the enrichment pipeline.

---

## Revert Checklist

When the long-term fix is deployed, revert these temporary workarounds:

- [ ] Restore PM-series trials: `UPDATE trials SET avoid_search = false WHERE id IN (299985, 574420);`
- [ ] Review any other `avoid_search = true` flags set for demo purposes
- [ ] Remove hardcoded investigator filters if any were added
