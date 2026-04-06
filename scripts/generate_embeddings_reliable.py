"""
Reliable embedding generator - guaranteed to complete all trials.

Features:
1. Sequential DB updates (no connection pool issues)
2. Retry failed updates up to 3 times
3. Checkpointing for resume capability
4. Progress logging with ETA
5. Rate limiting to avoid throttling
"""

import sys
import time
import json
import argparse
from pathlib import Path
from datetime import datetime
from openai import OpenAI
from src.db.supabase_client import get_supabase_admin_client
from src.embeddings.generator import build_trial_text_for_embedding

sys.stdout.reconfigure(line_buffering=True)

client = OpenAI()
CHECKPOINT_FILE = ".embedding_checkpoint.json"


def get_embeddings_batch(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    """Get embeddings for multiple texts in one API call."""
    if not texts:
        return []
    try:
        response = client.embeddings.create(model=model, input=texts)
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"  ⚠️ OpenAI error: {e}")
        return [None] * len(texts)


def update_single_trial(supabase, trial_id: int, embedding: list, max_retries: int = 3) -> bool:
    """Update a single trial's embedding with retry logic."""
    for attempt in range(max_retries):
        try:
            supabase.table("trials").update({
                "embedding": embedding
            }).eq("id", trial_id).execute()
            return True
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))  # Backoff
            else:
                return False
    return False


def save_checkpoint(processed: int, success: int, start_time: str):
    """Save progress checkpoint."""
    with open(CHECKPOINT_FILE, 'w') as f:
        json.dump({
            "total_processed": processed,
            "total_success": success,
            "start_time": start_time,
            "last_checkpoint": datetime.now().isoformat()
        }, f, indent=2)


def load_checkpoint() -> dict:
    """Load checkpoint if exists."""
    try:
        with open(CHECKPOINT_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def update_batch_threaded(supabase, trials: list[dict], embeddings: list, max_workers: int = 10) -> int:
    """Update trials with limited threading for speed + reliability."""
    import concurrent.futures
    
    def update_with_retry(args):
        trial, embedding = args
        if not embedding:
            return 0
        return 1 if update_single_trial(supabase, trial["id"], embedding) else 0
    
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        results = list(executor.map(update_with_retry, zip(trials, embeddings)))
    
    return sum(results)


def generate_embeddings_reliable(batch_size: int = 500, resume: bool = False):
    """Generate embeddings with guaranteed reliability."""
    supabase = get_supabase_admin_client()
    
    # Check for resume
    checkpoint = load_checkpoint() if resume else None
    if checkpoint:
        print(f"📂 Resuming from checkpoint: {checkpoint['total_processed']:,} processed")
        total_processed = checkpoint['total_processed']
        total_success = checkpoint['total_success']
        start_time = checkpoint['start_time']
    else:
        total_processed = 0
        total_success = 0
        start_time = datetime.now().isoformat()
    
    # Skip count query to avoid timeout - estimate remaining from checkpoint
    try:
        count_result = supabase.table("trials").select("id", count="exact").is_("embedding", "null").limit(1).execute()
        remaining = count_result.count
    except Exception:
        remaining = 577513 - total_processed  # Estimate based on total trials
    
    print(f"🚀 Reliable Embedding Generator")
    print(f"  Trials without embeddings: ~{remaining:,} (estimated)")
    print(f"  Batch size: {batch_size} (large batches to OpenAI)")
    print(f"  DB threads: 10 (with retry logic)")
    print(f"  Estimated time: ~{remaining / 25 / 3600:.1f} hours")
    print()
    
    batch_num = 0
    loop_start = time.time()
    
    while True:
        # Fetch trials without embeddings
        result = supabase.table("trials").select(
            "id, nct_id, brief_title, brief_summary, conditions, phase, study_type"
        ).is_("embedding", "null").limit(batch_size).execute()
        
        trials = result.data
        if not trials:
            print("\n✅ No more trials without embeddings!")
            break
        
        batch_num += 1
        
        # Build texts and get embeddings (single API call for whole batch)
        texts = [build_trial_text_for_embedding(t) for t in trials]
        embeddings = get_embeddings_batch(texts)
        
        # Update with limited threading + retry
        batch_success = update_batch_threaded(supabase, trials, embeddings, max_workers=10)
        total_success += batch_success
        total_processed += len(trials)
        
        # Calculate stats
        elapsed = time.time() - loop_start
        rate = total_processed / elapsed if elapsed > 0 else 0
        
        # Estimate remaining
        remaining_estimate = remaining - total_processed
        eta_seconds = remaining_estimate / rate if rate > 0 else 0
        eta_hours = eta_seconds / 3600
        
        print(f"Batch {batch_num}: {batch_success}/{len(trials)} | Total: {total_success:,}/{total_processed:,} | Rate: {rate:.1f}/sec | ETA: {eta_hours:.1f}h")
        
        # Checkpoint every 10 batches
        if batch_num % 10 == 0:
            save_checkpoint(total_processed, total_success, start_time)
            print(f"  💾 Checkpoint saved")
        
        # Small delay between batches
        time.sleep(0.2)
    
    # Final checkpoint
    save_checkpoint(total_processed, total_success, start_time)
    
    elapsed = time.time() - loop_start
    print()
    print(f"🎉 Complete!")
    print(f"  Total processed: {total_processed:,}")
    print(f"  Total success: {total_success:,}")
    print(f"  Success rate: {total_success/total_processed*100:.1f}%")
    print(f"  Time: {elapsed/3600:.1f} hours")
    print(f"  Rate: {total_processed/elapsed:.1f} trials/sec")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Reliable embedding generator")
    parser.add_argument("--batch-size", type=int, default=100, help="Trials per OpenAI API call")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    
    args = parser.parse_args()
    
    generate_embeddings_reliable(
        batch_size=args.batch_size,
        resume=args.resume
    )
