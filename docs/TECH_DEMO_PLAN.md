# Volta Tech Demo Script — 3 Minutes

**Date**: May 17, 2026  
**Duration**: 3 minutes  
**Flow**: PI Finder → Protocol Analyzer → Future Vision  
**Demo Query**: "Phase 2 trial of PM060184 for Colorectal Cancer after standard treatment"

---

## Why PI Finder First?

Sponsors don't have finalized protocols during early site selection. They have:
- A protocol synopsis
- A draft protocol
- A scientific description
- An IND draft section
- A plain-English description of the therapy

**PI Finder works with just a description. Protocol Analyzer works when you have the full document.**

---

## Full Demo Script (3 Minutes)

---

### **0:00–0:20 | Problem Statement**

**Say**:
> "86% of clinical trials fail to meet enrollment timelines. 30% fail for operational reasons — not scientific ones. The problem starts before the trial even begins: sponsors pick the wrong sites, miss protocol risks, and waste months on feasibility. Volta fixes this."

**Action**: Have the PI Finder chat open and ready.

---

### **0:20–1:00 | PI Finder Demo**

**Say**:
> "Let's say I'm a sponsor with a new oncology drug and I need to select a physican (PI) and site to run my trial. I don't have a finalized protocol yet — just a description. I type: 'Phase 2 trial of PM060184 for Colorectal Cancer after standard treatment.'"

**Action**: Type or paste the query. Results appear with Dr. Peirong Ding at the top.

**Say**:
> "Volta returns ranked investigators matched to my trial concept. Dr. Peirong Ding is our top match."

**Say** (explaining the tech):
> "Under the hood, we've centralized and embedded over 550,000 clinical trials covering conditions, trial summaries, mechnasism of action of the drug, PI info, and much more. When a sponsor types a query, we convert it to a vector and find the most similar trials. Then we identify which investigators ran those trials and rank them using a scoring function that includes PI's disease-area match, phase experience, and completion rates."

**Say**:
> "We're actively enriching our data by scraping data from Lancet, New Enland Journal of Medicine, and the endless FDA websites. We are also experimenting with new ways to improve our recommendations algorithms."

**Action**: Click to ask for more info on Dr. Ding.

**Say**:
> "I can ask for more details. Here's Dr. Ding's trial history, and as you can see he has strong experience in clinical trials with cancer including colorectal cancer. His contact information is also provided."

---

### **1:00–2:15 | Protocol Analyzer Demo**

**Say**:
> "Now let's say I have the full protocol document. I upload it to our Protocol Analyzer."

**Action**: Navigate to Protocol Intelligence. Upload or show pre-loaded PM060184 analysis.

**Say**:
> "Volta parses the protocol and scores it across multiple dimensions. Let me walk you through what it found."

**Point to Enrollment Difficulty (Very High: 73)**:

**Say**:
> "Enrollment Difficulty is very high, it scored 73 out of 100. This is because the trial requires third-line patients, people who've already failed two prior treatments. "In oncology, 'line of therapy' refers to the sequence of treatments. First-line is the initial treatment. Third-line means the patient has already failed two prior regimens. These patients are sicker and harder to recruit."

**Point to ECOG 0-1 requirement**:

**Say**:
> "Here's a protocol mismatch Volta caught: the trial requires ECOG 0-1 — meaning patients who are fully active or only slightly restricted. But third-line patients are typically ECOG 2 or higher. This eligibility criteria will screen out the very patients the trial needs. That's a red flag."

**Point to Site Burden (High: 60)**:

**Say**:
> "Site Burden is high. The protocol requires imaging every 6 weeks and intensive PK sampling. Sites need dedicated research nursing and central imaging connectivity."

**Point to Patient Burden (High: 50)**:

**Say**:
> "Patient Burden is also elevated — frequent visits and blood draws for a population that's already fatigued from prior treatments."

**Point to Feasibility Questions**:

**Say**:
> "And here are auto-generated feasibility questions for site outreach: 'How many third-line colorectal patients do you see annually?' 'Do you have research nursing for intensive PK sampling?' These are the questions you'd ask during this process — Volta generates them automatically."

---

### **2:15–3:00 | Future Vision & Close**

**Say**:
> "What you've seen is site intelligence and protocol intelligence, two steps of a multi-year clinical trial process. But clinical trials have many more operational stages, and they're all expensive."

**Say**:
> "Legacy CROs charge $15 million for a Phase 1 trial and $25 to $40 million for Phase 2. Phase 3 can exceed $100 million. Source data verification and case report forms alone account for 20 to 40 percent of trial costs."

**Say**:
> "Volta's vision is to automate the entire operational lifecycle: site selection, protocol optimization, protocol design, CRF generation, risk-based monitoring, and real-time trial oversight. Each stage feeds structured data to the next."

**Say** (closing):
> "Our long-term goal is to cut the path from drug candidate to approved therapy in half. Additionally, as our proprietary clinical data and operational knowledge grows, we can acquire undervalued assets and bring them to market through our own infrastructure. More drugs reach patients. More lives saved. That's Volta."

---

## Timing Summary

| Time | Section | Duration |
|------|---------|----------|
| 0:00–0:20 | Problem Statement | 20 sec |
| 0:20–1:00 | PI Finder + Tech Explanation | 40 sec |
| 1:00–2:15 | Protocol Analyzer Deep Dive | 75 sec |
| 2:15–3:00 | Future Vision + Close | 45 sec |
| **Total** | | **3:00** |

---

## Key Technical Points to Hit

### Embedding Process (Current)
- 550K+ trials embedded
- Each embedding includes: title, summary, conditions, phase, study type
- Model: OpenAI text-embedding-3-small (1536 dimensions)

### Embedding Process (In Progress)
- Adding: PI names, drug names, mechanism of action, drug class
- Planned model: Voyage-3.5-lite (1024 dimensions, better retrieval)

### Ranking Process
1. User query → vector embedding
2. Similarity search against trial embeddings
3. Retrieve top similar trials
4. Identify PIs who ran those trials
5. Apply scoring function:
   - Semantic similarity (35%)
   - Disease-area match (20%)
   - Phase experience (10%)
   - Trial volume (15%)
   - Completion rate (5%)
   - Role confidence (15%)

---

## Key Domain Terms to Explain

### Line of Therapy
- **1L (First-line)**: Initial treatment for newly diagnosed cancer
- **2L (Second-line)**: Treatment after first-line fails
- **3L+ (Third-line+)**: Treatment after multiple prior regimens fail
- **Key insight**: 3L+ patients are sicker, rarer, harder to recruit

### ECOG Performance Status
- **Scale**: 0 (fully active) to 5 (dead)
- **ECOG 0**: Fully active, no restrictions
- **ECOG 1**: Restricted but ambulatory, can do light work
- **ECOG 2**: Ambulatory, capable of self-care, but unable to work
- **ECOG 3-4**: Limited self-care, confined to bed/chair
- **Key insight**: 3L+ patients are typically ECOG 2+, so requiring ECOG 0-1 creates a mismatch

---

## Cost Numbers to Mention

| Phase | Legacy CRO Cost |
|-------|-----------------|
| Phase 1 | $15M |
| Phase 2 | $25M–$40M |
| Phase 3 | $20M–$100M+ |
| SDV + CRF | 20–40% of trial cost |

---

## Pre-Demo Checklist

- [ ] PI Finder chat ready with query pre-typed
- [ ] Dr. Peirong Ding appears as top result
- [ ] Protocol Analyzer has PM060184 analysis loaded
- [ ] Enrollment Difficulty shows 73 (Very High)
- [ ] ECOG 0-1 mismatch visible in bottlenecks
- [ ] Feasibility questions section visible
- [ ] Practice run completed in under 3 minutes

---

## If Something Breaks

| Issue | Backup |
|-------|--------|
| PI search slow | Have screenshot ready |
| Wrong PI at top | Explain ranking is being refined |
| Protocol upload fails | Use pre-loaded analysis |
| Scores look wrong | Focus on bottlenecks section |

---

*Demo duration: 3 minutes*  
*Last updated: May 17, 2026*
