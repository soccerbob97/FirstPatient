"""Compute investigator metrics from trial data."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.db.supabase_client import get_supabase_admin_client


def compute_investigator_metrics():
    """
    Compute metrics for each investigator based on their trial history.
    
    Metrics computed:
    - total_trials: Number of trials the investigator has been involved in
    - completion_rate: Percentage of trials that reached COMPLETED status
    """
    client = get_supabase_admin_client()
    
    print("Fetching investigators...")
    investigators = client.table("investigators").select("id, full_name").execute()
    print(f"Found {len(investigators.data)} investigators")
    
    metrics_to_insert = []
    
    for i, inv in enumerate(investigators.data):
        inv_id = inv["id"]
        
        # Get all trials for this investigator
        trials_result = client.table("trial_investigators").select(
            "trials(id, overall_status)"
        ).eq("investigator_id", inv_id).execute()
        
        trials = [t["trials"] for t in trials_result.data if t.get("trials")]
        total_trials = len(trials)
        
        if total_trials == 0:
            continue
        
        # Count completed trials
        completed = sum(1 for t in trials if t.get("overall_status") == "COMPLETED")
        completion_rate = completed / total_trials if total_trials > 0 else 0
        
        metrics_to_insert.append({
            "investigator_id": inv_id,
            "total_trials": total_trials,
            "completion_rate": round(completion_rate, 3),
        })
        
        if (i + 1) % 100 == 0:
            print(f"Processed {i + 1}/{len(investigators.data)} investigators...")
    
    print(f"\nInserting metrics for {len(metrics_to_insert)} investigators...")
    
    # Clear existing metrics
    client.table("investigator_metrics").delete().neq("investigator_id", 0).execute()
    
    # Insert in batches
    batch_size = 100
    for i in range(0, len(metrics_to_insert), batch_size):
        batch = metrics_to_insert[i:i + batch_size]
        client.table("investigator_metrics").insert(batch).execute()
        print(f"Inserted batch {i // batch_size + 1}")
    
    print("\nDone!")
    
    # Show some stats
    if metrics_to_insert:
        avg_trials = sum(m["total_trials"] for m in metrics_to_insert) / len(metrics_to_insert)
        avg_completion = sum(m["completion_rate"] for m in metrics_to_insert) / len(metrics_to_insert)
        max_trials = max(m["total_trials"] for m in metrics_to_insert)
        
        print(f"\nStats:")
        print(f"  Investigators with metrics: {len(metrics_to_insert)}")
        print(f"  Average trials per PI: {avg_trials:.1f}")
        print(f"  Average completion rate: {avg_completion:.1%}")
        print(f"  Max trials for a single PI: {max_trials}")


if __name__ == "__main__":
    compute_investigator_metrics()
