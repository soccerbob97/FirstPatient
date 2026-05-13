#!/usr/bin/env python3
"""
Step 5: Generate Embeddings

Generates Voyage-3.5-lite embeddings (1024 dimensions) for subset trials.
Inserts into trials_embeddings_v2_test table.

Requirements:
    - VOYAGE_API_KEY in .env
    - pip install voyageai

Usage:
    PYTHONPATH=. python scripts/v2_test/05_generate_embeddings.py
    PYTHONPATH=. python scripts/v2_test/05_generate_embeddings.py --limit 100  # Test with small batch
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.db.supabase_client import get_supabase_admin_client

DATA_DIR = Path(__file__).parent / "data"

# Voyage API configuration
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
VOYAGE_MODEL = "voyage-3.5-lite"
VOYAGE_DIMENSIONS = 1024
BATCH_SIZE = 128  # Voyage supports up to 128 texts per batch


def load_subset_trial_ids() -> list[int]:
    """Load trial IDs from previous step."""
    ids_file = DATA_DIR / "subset_trial_ids.json"
    
    if not ids_file.exists():
        print(f"❌ Error: {ids_file} not found!")
        print("   Run 02_get_subset_trials.py first.")
        sys.exit(1)
    
    with open(ids_file) as f:
        return json.load(f)


def build_embedding_text(trial: dict, supabase) -> str:
    """
    Build the embedding text for a trial.
    Includes: title, summary, conditions, interventions, lead PI, lead sites.
    """
    parts = []
    
    # Title and summary
    if trial.get("brief_title"):
        parts.append(f"Title: {trial['brief_title']}")
    if trial.get("brief_summary"):
        # Truncate summary to avoid token limits
        summary = trial["brief_summary"][:1000]
        parts.append(f"Summary: {summary}")
    
    # Conditions
    conditions = trial.get("conditions") or []
    if conditions:
        parts.append(f"Conditions: {', '.join(conditions[:10])}")
    
    # Phase
    if trial.get("phase"):
        parts.append(f"Phase: {trial['phase']}")
    
    # Get interventions (if available)
    try:
        interventions = supabase.table("interventions").select(
            "name, type"
        ).eq("trial_id", trial["id"]).limit(5).execute()
        
        if interventions.data:
            intervention_strs = [
                f"{i['name']} ({i['type']})" if i.get('type') else i['name']
                for i in interventions.data
            ]
            parts.append(f"Interventions: {', '.join(intervention_strs)}")
    except:
        pass
    
    # Get lead PI
    try:
        pi_links = supabase.table("trial_investigators").select(
            "investigator_id, role"
        ).eq("trial_id", trial["id"]).eq("role", "PRINCIPAL_INVESTIGATOR").limit(1).execute()
        
        if pi_links.data:
            pi = supabase.table("investigators").select(
                "full_name, therapeutic_areas"
            ).eq("id", pi_links.data[0]["investigator_id"]).single().execute()
            
            if pi.data:
                parts.append(f"Lead PI: {pi.data['full_name']}")
                if pi.data.get("therapeutic_areas"):
                    parts.append(f"PI expertise: {', '.join(pi.data['therapeutic_areas'][:3])}")
    except:
        pass
    
    # Get lead sites
    try:
        site_links = supabase.table("trial_sites").select(
            "site_id"
        ).eq("trial_id", trial["id"]).limit(3).execute()
        
        if site_links.data:
            site_ids = [s["site_id"] for s in site_links.data]
            sites = supabase.table("sites").select(
                "facility_name, country"
            ).in_("id", site_ids).execute()
            
            if sites.data:
                site_strs = [
                    f"{s['facility_name']}, {s['country']}" if s.get('country') else s['facility_name']
                    for s in sites.data
                ]
                parts.append(f"Sites: {'; '.join(site_strs)}")
    except:
        pass
    
    return "\n".join(parts)


def generate_voyage_embeddings(texts: list[str]) -> list[list[float]]:
    """Generate embeddings using Voyage API."""
    try:
        import voyageai
    except ImportError:
        print("❌ voyageai not installed. Run: pip install voyageai")
        sys.exit(1)
    
    client = voyageai.Client(api_key=VOYAGE_API_KEY)
    
    result = client.embed(
        texts,
        model=VOYAGE_MODEL,
        input_type="document",
        output_dimension=VOYAGE_DIMENSIONS
    )
    
    return result.embeddings


def main(args):
    print("🚀 Generating Voyage-3.5-lite embeddings for subset trials...")
    
    if not VOYAGE_API_KEY:
        print("❌ VOYAGE_API_KEY not found in .env")
        print("   Get a key from: https://www.voyageai.com/")
        return
    
    print(f"✅ Voyage API key found")
    print(f"   Model: {VOYAGE_MODEL}")
    print(f"   Dimensions: {VOYAGE_DIMENSIONS}")
    
    supabase = get_supabase_admin_client()
    
    # Load subset trial IDs
    trial_ids = load_subset_trial_ids()
    print(f"\n📋 Loaded {len(trial_ids):,} trial IDs")
    
    if args.limit:
        trial_ids = trial_ids[:args.limit]
        print(f"   Limited to {len(trial_ids):,} (--limit {args.limit})")
    
    # Check which trials already have embeddings
    print("\n🔍 Checking existing embeddings...")
    existing_ids = set()
    for i in range(0, len(trial_ids), 500):
        batch = trial_ids[i:i + 500]
        result = supabase.table("trials_embeddings_v2_test").select(
            "trial_id"
        ).in_("trial_id", batch).execute()
        existing_ids.update(r["trial_id"] for r in result.data)
    
    trial_ids = [tid for tid in trial_ids if tid not in existing_ids]
    print(f"   Already embedded: {len(existing_ids):,}")
    print(f"   To embed: {len(trial_ids):,}")
    
    if not trial_ids:
        print("\n✅ All trials already have embeddings!")
        return
    
    # Fetch trial data and build embedding texts
    print("\n📥 Fetching trial data and building embedding texts...")
    trials_data = []
    
    for i in range(0, len(trial_ids), 100):
        batch_ids = trial_ids[i:i + 100]
        result = supabase.table("trials").select(
            "id, brief_title, brief_summary, conditions, phase"
        ).in_("id", batch_ids).execute()
        
        for trial in result.data:
            embedding_text = build_embedding_text(trial, supabase)
            trials_data.append({
                "trial_id": trial["id"],
                "embedding_text": embedding_text
            })
        
        print(f"   Processed {len(trials_data):,}/{len(trial_ids):,} trials")
    
    # Generate embeddings in batches
    print(f"\n🔄 Generating embeddings (batch size: {BATCH_SIZE})...")
    total_embedded = 0
    total_failed = 0
    
    for i in range(0, len(trials_data), BATCH_SIZE):
        batch = trials_data[i:i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        total_batches = (len(trials_data) + BATCH_SIZE - 1) // BATCH_SIZE
        
        print(f"\n   Batch {batch_num}/{total_batches} ({len(batch)} trials)")
        
        try:
            # Generate embeddings
            texts = [t["embedding_text"] for t in batch]
            embeddings = generate_voyage_embeddings(texts)
            
            # Insert into database
            for j, (trial_data, embedding) in enumerate(zip(batch, embeddings)):
                try:
                    supabase.table("trials_embeddings_v2_test").upsert({
                        "trial_id": trial_data["trial_id"],
                        "embedding": embedding,
                        "embedding_text": trial_data["embedding_text"],
                        "created_at": datetime.now().isoformat()
                    }).execute()
                    total_embedded += 1
                except Exception as e:
                    print(f"      Error inserting trial {trial_data['trial_id']}: {e}")
                    total_failed += 1
            
            print(f"   ✓ Embedded: {len(batch)}")
            
            # Rate limiting (Voyage has generous limits but be safe)
            time.sleep(0.5)
            
        except Exception as e:
            print(f"   ❌ Batch failed: {e}")
            total_failed += len(batch)
    
    # Summary
    print(f"\n{'='*50}")
    print(f"✅ Embedding generation complete!")
    print(f"   Total embedded: {total_embedded:,}")
    print(f"   Failed: {total_failed:,}")
    print(f"   Table: trials_embeddings_v2_test")
    print("\n✅ Complete! Next: run 06_test_search.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Voyage embeddings for subset trials")
    parser.add_argument("--limit", type=int, help="Limit number of trials to process")
    
    args = parser.parse_args()
    main(args)
