"""Generate embeddings for trials and investigators in the database."""

import asyncio
import argparse
from typing import List

from src.db.supabase_client import get_supabase_admin_client
from src.embeddings.generator import (
    get_embedding,
    get_embeddings_batch,
    build_trial_text_for_embedding,
    build_investigator_expertise_profile,
)


def generate_trial_embeddings(batch_size: int = 50, limit: int = None):
    """
    Generate embeddings for all trials without embeddings.
    
    Args:
        batch_size: Number of trials to process at once
        limit: Max trials to process (None = all)
    """
    client = get_supabase_admin_client()
    
    total_processed = 0
    target = limit or float('inf')
    
    while total_processed < target:
        # Fetch batch of trials without embeddings (Supabase limits to 1000 per query)
        fetch_size = min(1000, int(target - total_processed)) if limit else 1000
        
        result = client.table("trials").select(
            "id, nct_id, brief_title, brief_summary, conditions, phase, study_type"
        ).is_("embedding", "null").limit(fetch_size).execute()
        
        trials = result.data
        
        if not trials:
            print("No more trials without embeddings")
            break
        
        print(f"Fetched {len(trials)} trials without embeddings (total processed: {total_processed})")
        
        # Process in batches
        for i in range(0, len(trials), batch_size):
            batch = trials[i:i + batch_size]
            
            # Build texts for embedding
            texts = [build_trial_text_for_embedding(t) for t in batch]
            
            # Generate embeddings
            embeddings = get_embeddings_batch(texts)
            
            # Update database
            for trial, embedding in zip(batch, embeddings):
                if embedding:
                    client.table("trials").update({
                        "embedding": embedding
                    }).eq("id", trial["id"]).execute()
            
            total_processed += len(batch)
            print(f"Processed {total_processed} trials")
            
            if total_processed >= target:
                break
    
    print(f"Trial embeddings complete! Total: {total_processed}")


def generate_investigator_embeddings(batch_size: int = 20, limit: int = None):
    """
    Generate expertise profiles and embeddings for investigators.
    
    Args:
        batch_size: Number of investigators to process at once
        limit: Max investigators to process (None = all)
    """
    client = get_supabase_admin_client()
    
    # Get investigators without embeddings
    query = client.table("investigators").select("id, full_name, affiliation").is_("embedding", "null")
    
    if limit:
        query = query.limit(limit)
    
    result = query.execute()
    investigators = result.data
    
    print(f"Found {len(investigators)} investigators without embeddings")
    
    if not investigators:
        return
    
    # Process in batches
    for i in range(0, len(investigators), batch_size):
        batch = investigators[i:i + batch_size]
        
        profiles = []
        for inv in batch:
            # Get trials for this investigator
            trials_result = client.table("trial_investigators").select(
                "trials(id, brief_title, conditions, phase, lead_sponsor_class)"
            ).eq("investigator_id", inv["id"]).execute()
            
            trials = [t["trials"] for t in trials_result.data if t.get("trials")]
            
            # Build expertise profile
            profile = build_investigator_expertise_profile(inv, trials)
            profiles.append(profile)
            
            # Update expertise_profile in database
            if profile:
                client.table("investigators").update({
                    "expertise_profile": profile
                }).eq("id", inv["id"]).execute()
        
        # Generate embeddings for profiles
        embeddings = get_embeddings_batch([p for p in profiles if p])
        
        # Update embeddings
        embedding_idx = 0
        for inv, profile in zip(batch, profiles):
            if profile:
                embedding = embeddings[embedding_idx]
                embedding_idx += 1
                
                if embedding:
                    client.table("investigators").update({
                        "embedding": embedding
                    }).eq("id", inv["id"]).execute()
        
        print(f"Processed {min(i + batch_size, len(investigators))}/{len(investigators)} investigators")
    
    print("Investigator embeddings complete!")


def main():
    parser = argparse.ArgumentParser(description="Generate embeddings for trials and investigators")
    parser.add_argument(
        "--trials-only",
        action="store_true",
        help="Only generate trial embeddings"
    )
    parser.add_argument(
        "--investigators-only",
        action="store_true",
        help="Only generate investigator embeddings"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=50,
        help="Batch size for processing (default: 50)"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of records to process"
    )
    
    args = parser.parse_args()
    
    if args.investigators_only:
        generate_investigator_embeddings(batch_size=args.batch_size, limit=args.limit)
    elif args.trials_only:
        generate_trial_embeddings(batch_size=args.batch_size, limit=args.limit)
    else:
        # Generate both
        generate_trial_embeddings(batch_size=args.batch_size, limit=args.limit)
        generate_investigator_embeddings(batch_size=min(args.batch_size, 20), limit=args.limit)


if __name__ == "__main__":
    main()
