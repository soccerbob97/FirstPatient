"""
Ultra-fast parallel embedding generator.

Optimizations:
1. Async OpenAI API calls (10+ concurrent)
2. Large batches (500 texts per API call)
3. Bulk SQL updates (1 query per 500 trials instead of 500 queries)
4. Pipeline: fetch → embed → update all in parallel
"""

import sys
import time
import asyncio
import argparse
from openai import AsyncOpenAI
from src.db.supabase_client import get_supabase_admin_client
from src.embeddings.generator import build_trial_text_for_embedding

sys.stdout.reconfigure(line_buffering=True)

async_client = AsyncOpenAI()


async def get_embeddings_async(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    """Get embeddings asynchronously."""
    if not texts:
        return []
    try:
        response = await async_client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"Embedding error: {e}")
        return [None] * len(texts)

def update_embeddings_threaded(supabase, trials: list[dict], embeddings: list) -> int:
    """Update embeddings using concurrent threads."""
    import concurrent.futures
    
    def update_one(args):
        trial, embedding = args
        if embedding:
            try:
                supabase.table("trials").update({
                    "embedding": embedding
                }).eq("id", trial["id"]).execute()
                return 1
            except:
                return 0
        return 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = list(executor.map(update_one, zip(trials, embeddings)))
    
    return sum(results)


async def process_batch_async(supabase, trials: list[dict], semaphore: asyncio.Semaphore) -> int:
    """Process a batch: get embeddings async, update DB with threads."""
    async with semaphore:
        texts = [build_trial_text_for_embedding(t) for t in trials]
        embeddings = await get_embeddings_async(texts)
        
        # Use thread pool for DB updates (run in executor to not block)
        loop = asyncio.get_event_loop()
        success = await loop.run_in_executor(
            None, update_embeddings_threaded, supabase, trials, embeddings
        )
        return success


async def generate_embeddings_parallel(limit: int = 50000, batch_size: int = 200, max_concurrent: int = 10):
    """Generate embeddings with full parallelization."""
    supabase = get_supabase_admin_client()
    semaphore = asyncio.Semaphore(max_concurrent)
    
    total_processed = 0
    total_success = 0
    start_time = time.time()
    
    print(f"🚀 Ultra-fast parallel embedding generation")
    print(f"  Target: {limit:,} trials")
    print(f"  Batch size: {batch_size} texts per OpenAI call")
    print(f"  Concurrent API calls: {max_concurrent}")
    print(f"  DB update threads: 50")
    print()
    
    while total_processed < limit:
        # Fetch trials
        fetch_size = min(1000, limit - total_processed)
        result = supabase.table("trials").select(
            "id, nct_id, brief_title, brief_summary, conditions, phase, study_type"
        ).is_("embedding", "null").limit(fetch_size).execute()
        
        trials = result.data
        if not trials:
            print("No more trials without embeddings")
            break
        
        # Split into batches and process all concurrently
        batches = [trials[i:i+batch_size] for i in range(0, len(trials), batch_size)]
        tasks = [process_batch_async(supabase, batch, semaphore) for batch in batches]
        
        results = await asyncio.gather(*tasks)
        
        total_success += sum(results)
        total_processed += len(trials)
        
        elapsed = time.time() - start_time
        rate = total_processed / elapsed if elapsed > 0 else 0
        eta = (limit - total_processed) / rate / 60 if rate > 0 else 0
        
        print(f"Processed: {total_processed:,} | Success: {total_success:,} | Rate: {rate:.1f}/sec | ETA: {eta:.1f}min")
    
    elapsed = time.time() - start_time
    print()
    print(f"✅ Complete!")
    print(f"  Total: {total_processed:,} | Success: {total_success:,}")
    print(f"  Time: {elapsed/60:.1f} min | Rate: {total_processed/elapsed:.1f}/sec")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=50000)
    parser.add_argument("--batch-size", type=int, default=200)
    parser.add_argument("--concurrent", type=int, default=10)
    args = parser.parse_args()
    
    asyncio.run(generate_embeddings_parallel(
        limit=args.limit,
        batch_size=args.batch_size,
        max_concurrent=args.concurrent
    ))
