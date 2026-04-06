"""
Embed trials by category for quick demo coverage.
Prioritizes common conditions so search works immediately.
"""

import sys
import time
from openai import OpenAI
from src.db.supabase_client import get_supabase_admin_client
from src.embeddings.generator import build_trial_text_for_embedding

sys.stdout.reconfigure(line_buffering=True)

client = OpenAI()

# Categories to prioritize (search terms)
CATEGORIES = [
    ("Cancer/Oncology", ["cancer", "oncology", "tumor", "carcinoma", "leukemia", "lymphoma"]),
    ("Diabetes", ["diabetes", "diabetic", "glucose", "insulin"]),
    ("Cardiovascular", ["heart", "cardiac", "cardiovascular", "hypertension", "stroke"]),
    ("Alzheimer's/Neuro", ["alzheimer", "dementia", "parkinson", "neurological"]),
    ("Respiratory", ["lung", "respiratory", "asthma", "copd", "pulmonary"]),
    ("Infectious Disease", ["covid", "hiv", "hepatitis", "infection", "vaccine"]),
]


def get_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """Get embeddings for batch."""
    if not texts:
        return []
    try:
        response = client.embeddings.create(model="text-embedding-3-small", input=texts)
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"  ⚠️ Error: {e}")
        return [None] * len(texts)


def update_single(supabase, trial_id: int, embedding: list) -> bool:
    """Update single trial with retry."""
    for attempt in range(3):
        try:
            supabase.table("trials").update({"embedding": embedding}).eq("id", trial_id).execute()
            return True
        except:
            time.sleep(0.3 * (attempt + 1))
    return False


def embed_category(supabase, category_name: str, search_terms: list[str], limit: int = 2000):
    """Embed trials for a specific category."""
    print(f"\n📁 {category_name}")
    
    # Build OR query for search terms
    or_conditions = ",".join([f"brief_title.ilike.%{term}%" for term in search_terms])
    
    # Fetch trials without embeddings matching this category
    result = supabase.table("trials").select(
        "id, nct_id, brief_title, brief_summary, conditions, phase, study_type"
    ).is_("embedding", "null").or_(or_conditions).limit(limit).execute()
    
    trials = result.data
    if not trials:
        print(f"  No trials found (or all already embedded)")
        return 0
    
    print(f"  Found {len(trials)} trials to embed")
    
    # Process in batches of 500 (OpenAI supports up to 2048)
    total_success = 0
    batch_size = 500
    
    for i in range(0, len(trials), batch_size):
        batch = trials[i:i+batch_size]
        texts = [build_trial_text_for_embedding(t) for t in batch]
        embeddings = get_embeddings_batch(texts)
        
        batch_success = 0
        for trial, emb in zip(batch, embeddings):
            if emb and update_single(supabase, trial["id"], emb):
                batch_success += 1
        
        total_success += batch_success
        print(f"  Batch {i//batch_size + 1}: {batch_success}/{len(batch)} | Total: {total_success}")
    
    return total_success


def run_full_embedding(supabase):
    """Run full embedding on remaining trials."""
    print("\n" + "=" * 50)
    print("🚀 Starting FULL embedding of remaining trials...")
    print("=" * 50)
    
    batch_size = 500
    total_processed = 0
    total_success = 0
    start = time.time()
    
    while True:
        # Fetch trials without embeddings
        result = supabase.table("trials").select(
            "id, nct_id, brief_title, brief_summary, conditions, phase, study_type"
        ).is_("embedding", "null").limit(batch_size).execute()
        
        trials = result.data
        if not trials:
            print("\n✅ No more trials without embeddings!")
            break
        
        texts = [build_trial_text_for_embedding(t) for t in trials]
        embeddings = get_embeddings_batch(texts)
        
        batch_success = 0
        for trial, emb in zip(trials, embeddings):
            if emb and update_single(supabase, trial["id"], emb):
                batch_success += 1
        
        total_success += batch_success
        total_processed += len(trials)
        
        elapsed = time.time() - start
        rate = total_processed / elapsed if elapsed > 0 else 0
        
        # Get remaining count every 10 batches
        if (total_processed // batch_size) % 10 == 0:
            count_result = supabase.table("trials").select("id", count="exact").is_("embedding", "null").limit(1).execute()
            remaining = count_result.count
            eta_hours = remaining / rate / 3600 if rate > 0 else 0
            print(f"Progress: {total_success:,}/{total_processed:,} | Rate: {rate:.1f}/sec | Remaining: {remaining:,} | ETA: {eta_hours:.1f}h")
        else:
            print(f"Progress: {total_success:,}/{total_processed:,} | Rate: {rate:.1f}/sec")
    
    elapsed = time.time() - start
    print()
    print(f"🎉 Full embedding complete!")
    print(f"  Total: {total_success:,}/{total_processed:,}")
    print(f"  Time: {elapsed/3600:.1f} hours")


def main():
    supabase = get_supabase_admin_client()
    
    print("🚀 Embedding trials by category for quick demo")
    print("=" * 50)
    
    start = time.time()
    total = 0
    
    for category_name, search_terms in CATEGORIES:
        count = embed_category(supabase, category_name, search_terms, limit=2000)
        total += count
    
    elapsed = time.time() - start
    print()
    print("=" * 50)
    print(f"✅ Categories complete! Embedded {total:,} trials in {elapsed/60:.1f} minutes")
    print(f"   Rate: {total/elapsed:.1f} trials/sec")
    
    # Now run full embedding on remaining trials
    run_full_embedding(supabase)


if __name__ == "__main__":
    main()
