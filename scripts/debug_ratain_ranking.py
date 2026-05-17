#!/usr/bin/env python3
"""Debug why Mark Ratain ranks so high for colorectal cancer query."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import math
from src.recommendations.recommender import PIRecommender
from src.embeddings.generator import get_embedding

r = PIRecommender()
query = "A Phase II, Open-label, Multicenter Study of PM060184 in Patients with Advanced Colorectal Cancer after Standard Treatment"

# Step 1: Get embedding and find similar trials
embedding = get_embedding(query)
result = r.client.rpc("match_trial_embeddings_full", {
    "query_embedding": embedding,
    "match_threshold": 0.3,
    "match_count": 20
})

print("=== SIMILAR TRIALS FOUND ===")
for row in result.data:
    tid = row["trial_id"]
    sim = row["similarity"]
    
    # Check if Mark Ratain (292492) is on this trial
    check = r.client.table("trial_investigators").select("id").eq(
        "trial_id", tid
    ).eq("investigator_id", 292492).limit(1).execute()
    
    trial_info = r.client.table("trials").select(
        "brief_title, phase, conditions"
    ).eq("id", tid).limit(1).execute()
    
    title = trial_info.data[0]["brief_title"][:80] if trial_info.data else "Unknown"
    phase = trial_info.data[0].get("phase", "N/A") if trial_info.data else "N/A"
    conditions = trial_info.data[0].get("conditions", []) if trial_info.data else []
    
    marker = "*** MARK RATAIN ***" if check.data else ""
    print(f"  Sim: {sim:.3f} | Phase: {phase} | {title} {marker}")
    if marker:
        print(f"    Conditions: {conditions}")

# Step 2: Show Mark Ratain's score breakdown
print("\n=== MARK RATAIN SCORE BREAKDOWN ===")
trials = 7
similarity = 0  # We'll find this from the results

# Find his similarity scores
for row in result.data:
    tid = row["trial_id"]
    sim = row["similarity"]
    check = r.client.table("trial_investigators").select("id").eq(
        "trial_id", tid
    ).eq("investigator_id", 292492).limit(1).execute()
    if check.data:
        similarity = max(similarity, sim)
        print(f"  Matched trial {tid} with similarity: {sim:.3f}")

experience_score = min(0.5 + 0.5 * math.log10(max(trials, 1) + 1) / math.log10(11), 1.0)
completion_rate = min(0.1 * trials, 0.8)
completion_score = max(completion_rate, 0.5)
link_score = 1.0  # PRINCIPAL_INVESTIGATOR

print(f"\n  Similarity score: {similarity:.3f} (weight: 0.60)")
print(f"  Experience score: {experience_score:.3f} (weight: 0.15) [7 trials]")
print(f"  Completion score: {completion_score:.3f} (weight: 0.10) [rate: {completion_rate:.1f}]")
print(f"  Link score:       {link_score:.3f} (weight: 0.15) [PRINCIPAL_INVESTIGATOR]")

final = 0.60 * similarity + 0.15 * experience_score + 0.10 * completion_score + 0.15 * link_score
print(f"\n  RAW final score:  {final:.3f}")
