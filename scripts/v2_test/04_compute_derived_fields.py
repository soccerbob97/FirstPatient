#!/usr/bin/env python3
"""
Step 4: Compute Derived Fields

Computes derived fields for investigators in the subset:
- therapeutic_areas (from linked trials)
- total_trials
- years_active
- primary_role

Usage:
    PYTHONPATH=. python scripts/v2_test/04_compute_derived_fields.py
"""

import os
import sys
import json
from pathlib import Path
from collections import Counter

from dotenv import load_dotenv

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.db.supabase_client import get_supabase_admin_client

DATA_DIR = Path(__file__).parent / "data"


def load_subset_investigator_ids() -> list[int]:
    """Load investigator IDs from previous step."""
    ids_file = DATA_DIR / "subset_investigator_ids.json"
    
    if not ids_file.exists():
        print(f"❌ Error: {ids_file} not found!")
        print("   Run 02_get_subset_trials.py first.")
        sys.exit(1)
    
    with open(ids_file) as f:
        return json.load(f)


def compute_therapeutic_areas(supabase, investigator_ids: list[int]) -> dict:
    """Compute therapeutic areas for each investigator from their trials."""
    print("\n🔬 Computing therapeutic areas...")
    
    results = {}
    batch_size = 100
    
    for i in range(0, len(investigator_ids), batch_size):
        batch_ids = investigator_ids[i:i + batch_size]
        
        for inv_id in batch_ids:
            try:
                # Get all trials for this investigator
                trial_links = supabase.table("trial_investigators").select(
                    "trial_id"
                ).eq("investigator_id", inv_id).execute()
                
                if not trial_links.data:
                    continue
                
                trial_ids = [t["trial_id"] for t in trial_links.data]
                
                # Get conditions from those trials
                trials = supabase.table("trials").select(
                    "conditions"
                ).in_("id", trial_ids[:100]).execute()  # Limit to avoid timeout
                
                # Count conditions
                condition_counts = Counter()
                for trial in trials.data:
                    conditions = trial.get("conditions") or []
                    for cond in conditions:
                        if cond:
                            condition_counts[cond] += 1
                
                # Top 5 therapeutic areas
                top_areas = [cond for cond, _ in condition_counts.most_common(5)]
                
                results[inv_id] = {
                    "therapeutic_areas": top_areas,
                    "total_trials": len(trial_ids),
                }
                
            except Exception as e:
                print(f"   Error for investigator {inv_id}: {e}")
        
        print(f"   Processed {min(i + batch_size, len(investigator_ids))}/{len(investigator_ids)}")
    
    return results


def compute_role_and_years(supabase, investigator_ids: list[int]) -> dict:
    """Compute primary role and years active for each investigator."""
    print("\n👤 Computing roles and years active...")
    
    results = {}
    batch_size = 100
    
    for i in range(0, len(investigator_ids), batch_size):
        batch_ids = investigator_ids[i:i + batch_size]
        
        for inv_id in batch_ids:
            try:
                # Get roles from trial_investigators
                roles = supabase.table("trial_investigators").select(
                    "role"
                ).eq("investigator_id", inv_id).execute()
                
                if roles.data:
                    role_counts = Counter(r["role"] for r in roles.data if r.get("role"))
                    primary_role = role_counts.most_common(1)[0][0] if role_counts else None
                else:
                    primary_role = None
                
                # Get years active from trial dates
                trial_links = supabase.table("trial_investigators").select(
                    "trial_id"
                ).eq("investigator_id", inv_id).limit(50).execute()
                
                if trial_links.data:
                    trial_ids = [t["trial_id"] for t in trial_links.data]
                    trials = supabase.table("trials").select(
                        "start_date"
                    ).in_("id", trial_ids).execute()
                    
                    years = set()
                    for trial in trials.data:
                        if trial.get("start_date"):
                            year = trial["start_date"][:4]
                            years.add(int(year))
                    
                    years_active = max(years) - min(years) + 1 if years else None
                else:
                    years_active = None
                
                results[inv_id] = {
                    "primary_role": primary_role,
                    "years_active": years_active,
                }
                
            except Exception as e:
                print(f"   Error for investigator {inv_id}: {e}")
        
        print(f"   Processed {min(i + batch_size, len(investigator_ids))}/{len(investigator_ids)}")
    
    return results


def update_investigators(supabase, therapeutic_data: dict, role_data: dict):
    """Update investigators with computed fields."""
    print("\n💾 Updating investigators in database...")
    
    updated = 0
    failed = 0
    
    all_ids = set(therapeutic_data.keys()) | set(role_data.keys())
    
    for inv_id in all_ids:
        try:
            update_data = {}
            
            if inv_id in therapeutic_data:
                update_data["therapeutic_areas"] = therapeutic_data[inv_id].get("therapeutic_areas", [])
                update_data["total_trials"] = therapeutic_data[inv_id].get("total_trials", 0)
            
            if inv_id in role_data:
                if role_data[inv_id].get("primary_role"):
                    update_data["primary_role"] = role_data[inv_id]["primary_role"]
                if role_data[inv_id].get("years_active"):
                    update_data["years_active"] = role_data[inv_id]["years_active"]
            
            if update_data:
                supabase.table("investigators").update(update_data).eq("id", inv_id).execute()
                updated += 1
                
        except Exception as e:
            print(f"   Error updating {inv_id}: {e}")
            failed += 1
    
    print(f"   ✅ Updated: {updated}")
    print(f"   ❌ Failed: {failed}")
    
    return updated, failed


def main():
    print("🚀 Computing derived fields for subset investigators...")
    
    supabase = get_supabase_admin_client()
    
    # Load subset investigator IDs
    investigator_ids = load_subset_investigator_ids()
    print(f"📋 Loaded {len(investigator_ids):,} investigator IDs")
    
    # Compute therapeutic areas and total_trials
    therapeutic_data = compute_therapeutic_areas(supabase, investigator_ids)
    
    # Compute primary role and years active
    role_data = compute_role_and_years(supabase, investigator_ids)
    
    # Update database
    updated, failed = update_investigators(supabase, therapeutic_data, role_data)
    
    # Summary
    print(f"\n{'='*50}")
    print(f"✅ Derived fields computed!")
    print(f"   Investigators updated: {updated:,}")
    print(f"   Failed: {failed:,}")
    print("\n✅ Complete! Next: run 05_generate_embeddings.py")


if __name__ == "__main__":
    main()
