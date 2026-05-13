"""
Extract training data for PI Success Prediction Model.

This script extracts (PI, Trial, Success) training examples from historical trials
for diabetes, breast cancer, and obesity conditions.

Success Label:
- 1 = Trial COMPLETED
- 0 = Trial TERMINATED, WITHDRAWN, or SUSPENDED

Features extracted:
- PI features: prior trial count, completion rate, condition experience
- Site features: site trial count, completion rate
- Trial features: phase, enrollment, sponsor type
"""

import os
import sys
from datetime import datetime
from collections import defaultdict
import json

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()

from src.db.supabase_client import get_supabase_admin_client

# Success/Failure status mapping
SUCCESS_STATUSES = {'COMPLETED'}
FAILURE_STATUSES = {'TERMINATED', 'WITHDRAWN', 'SUSPENDED'}
# Exclude: RECRUITING, NOT_YET_RECRUITING, ACTIVE_NOT_RECRUITING, ENROLLING_BY_INVITATION, UNKNOWN

# Target conditions for prototype
TARGET_CONDITIONS = ['diabetes', 'breast cancer', 'obesity']


def get_subset_trials(client, batch_size=1000):
    """
    Fetch trials matching target conditions with completion outcomes.
    Uses filter() for greater-than comparison for pagination.
    """
    print("Fetching trials with completion outcomes...")
    
    all_trials = []
    last_id = 0
    total_processed = 0
    
    while True:
        # Build query with cursor-based pagination
        query = client.table("trials").select(
            "id, nct_id, brief_title, conditions, phase, overall_status, "
            "enrollment, enrollment_type, lead_sponsor_class, "
            "start_date, completion_date"
        ).in_(
            "overall_status", list(SUCCESS_STATUSES | FAILURE_STATUSES)
        )
        
        # Add cursor filter if not first batch
        if last_id > 0:
            query = query.gt("id", last_id)
        
        result = query.order("id").limit(batch_size).execute()
        
        if not result.data:
            break
        
        # Update cursor
        last_id = result.data[-1]["id"]
        total_processed += len(result.data)
        
        # Filter for target conditions
        for trial in result.data:
            conditions = trial.get("conditions") or []
            conditions_lower = [c.lower() for c in conditions]
            
            # Check if any target condition matches
            for target in TARGET_CONDITIONS:
                if any(target in c for c in conditions_lower):
                    trial["_matched_condition"] = target
                    all_trials.append(trial)
                    break
        
        print(f"  Processed {total_processed} trials, found {len(all_trials)} matching...")
        
        if len(result.data) < batch_size:
            break
    
    print(f"Total matching trials: {len(all_trials)}")
    return all_trials


def get_trial_investigators(client, trial_ids, batch_size=500):
    """
    Fetch investigators for given trials.
    """
    print(f"Fetching investigators for {len(trial_ids)} trials...")
    
    all_investigators = []
    
    for i in range(0, len(trial_ids), batch_size):
        batch_ids = trial_ids[i:i + batch_size]
        
        result = client.table("trial_investigators").select(
            "trial_id, investigator_id, role, "
            "investigators(id, full_name, affiliation)"
        ).in_("trial_id", batch_ids).execute()
        
        all_investigators.extend(result.data or [])
        print(f"  Fetched investigators for trials {i} to {i + len(batch_ids)}...")
    
    return all_investigators


def get_trial_sites(client, trial_ids, batch_size=500):
    """
    Fetch sites for given trials.
    """
    print(f"Fetching sites for {len(trial_ids)} trials...")
    
    all_sites = []
    
    for i in range(0, len(trial_ids), batch_size):
        batch_ids = trial_ids[i:i + batch_size]
        
        result = client.table("trial_sites").select(
            "trial_id, site_id, recruitment_status, "
            "sites(id, facility_name, city, country, institution_type)"
        ).in_("trial_id", batch_ids).execute()
        
        all_sites.extend(result.data or [])
        print(f"  Fetched sites for trials {i} to {i + len(batch_ids)}...")
    
    return all_sites


def compute_historical_features(trials, trial_investigators, trial_sites):
    """
    Compute historical features for each PI at the time of each trial.
    
    This simulates what we would have known about a PI BEFORE a trial started.
    """
    print("Computing historical features...")
    
    # Sort trials by start_date to compute "prior" features
    trials_sorted = sorted(trials, key=lambda t: t.get("start_date") or "1900-01-01")
    
    # Build trial lookup
    trial_lookup = {t["id"]: t for t in trials_sorted}
    
    # Build investigator -> trials mapping
    inv_trials = defaultdict(list)
    for ti in trial_investigators:
        inv_id = ti.get("investigator_id")
        trial_id = ti.get("trial_id")
        if inv_id and trial_id and trial_id in trial_lookup:
            inv_trials[inv_id].append(trial_lookup[trial_id])
    
    # Build site -> trials mapping
    site_trials = defaultdict(list)
    for ts in trial_sites:
        site_id = ts.get("site_id")
        trial_id = ts.get("trial_id")
        if site_id and trial_id and trial_id in trial_lookup:
            site_trials[site_id].append(trial_lookup[trial_id])
    
    # Build training examples
    training_examples = []
    
    for ti in trial_investigators:
        inv_id = ti.get("investigator_id")
        trial_id = ti.get("trial_id")
        inv_data = ti.get("investigators")
        
        if not inv_id or not trial_id or trial_id not in trial_lookup:
            continue
        
        trial = trial_lookup[trial_id]
        trial_start = trial.get("start_date") or "1900-01-01"
        
        # Compute PI's historical features (trials BEFORE this one)
        prior_trials = [
            t for t in inv_trials[inv_id]
            if (t.get("start_date") or "1900-01-01") < trial_start
        ]
        
        prior_completed = sum(1 for t in prior_trials if t["overall_status"] in SUCCESS_STATUSES)
        prior_failed = sum(1 for t in prior_trials if t["overall_status"] in FAILURE_STATUSES)
        prior_total = prior_completed + prior_failed
        
        # Condition-specific experience
        trial_condition = trial.get("_matched_condition", "")
        prior_same_condition = sum(
            1 for t in prior_trials 
            if t.get("_matched_condition") == trial_condition
        )
        
        # Phase-specific experience
        trial_phase = trial.get("phase") or ""
        prior_same_phase = sum(
            1 for t in prior_trials
            if t.get("phase") == trial_phase
        )
        
        # Create training example
        example = {
            # Identifiers
            "trial_id": trial_id,
            "nct_id": trial.get("nct_id"),
            "investigator_id": inv_id,
            "investigator_name": inv_data.get("full_name") if inv_data else None,
            "role": ti.get("role"),
            
            # Label
            "label": 1 if trial["overall_status"] in SUCCESS_STATUSES else 0,
            "overall_status": trial["overall_status"],
            
            # PI Features
            "pi_prior_trials": prior_total,
            "pi_prior_completed": prior_completed,
            "pi_prior_completion_rate": prior_completed / prior_total if prior_total > 0 else 0.5,
            "pi_prior_same_condition": prior_same_condition,
            "pi_prior_same_phase": prior_same_phase,
            "pi_has_affiliation": 1 if inv_data and inv_data.get("affiliation") else 0,
            
            # Trial Features
            "trial_phase": trial_phase,
            "trial_condition": trial_condition,
            "trial_enrollment": trial.get("enrollment") or 0,
            "trial_sponsor_class": trial.get("lead_sponsor_class") or "UNKNOWN",
            
            # Role Features
            "role_is_pi": 1 if ti.get("role") == "PRINCIPAL_INVESTIGATOR" else 0,
            "role_is_director": 1 if ti.get("role") == "STUDY_DIRECTOR" else 0,
            "role_is_chair": 1 if ti.get("role") == "STUDY_CHAIR" else 0,
        }
        
        training_examples.append(example)
    
    print(f"Generated {len(training_examples)} training examples")
    return training_examples


def save_training_data(examples, output_path):
    """Save training data to JSON file."""
    
    # Compute statistics
    total = len(examples)
    positive = sum(1 for e in examples if e["label"] == 1)
    negative = total - positive
    
    print(f"\nTraining Data Statistics:")
    print(f"  Total examples: {total}")
    print(f"  Positive (COMPLETED): {positive} ({100*positive/total:.1f}%)")
    print(f"  Negative (FAILED): {negative} ({100*negative/total:.1f}%)")
    
    # Condition breakdown
    by_condition = defaultdict(lambda: {"total": 0, "positive": 0})
    for e in examples:
        cond = e["trial_condition"]
        by_condition[cond]["total"] += 1
        by_condition[cond]["positive"] += e["label"]
    
    print(f"\nBy Condition:")
    for cond, stats in by_condition.items():
        rate = 100 * stats["positive"] / stats["total"] if stats["total"] > 0 else 0
        print(f"  {cond}: {stats['total']} examples, {rate:.1f}% success rate")
    
    # Save to file
    with open(output_path, "w") as f:
        json.dump({
            "metadata": {
                "created_at": datetime.now().isoformat(),
                "total_examples": total,
                "positive_examples": positive,
                "negative_examples": negative,
                "conditions": TARGET_CONDITIONS,
            },
            "examples": examples
        }, f, indent=2, default=str)
    
    print(f"\nSaved to {output_path}")


def main():
    print("=" * 60)
    print("PI Success Prediction - Training Data Extraction")
    print("=" * 60)
    
    client = get_supabase_admin_client()
    
    # Step 1: Get subset trials
    trials = get_subset_trials(client)
    
    if not trials:
        print("No matching trials found!")
        return
    
    trial_ids = [t["id"] for t in trials]
    
    # Step 2: Get investigators and sites
    trial_investigators = get_trial_investigators(client, trial_ids)
    trial_sites = get_trial_sites(client, trial_ids)
    
    # Step 3: Compute historical features
    training_examples = compute_historical_features(trials, trial_investigators, trial_sites)
    
    # Step 4: Save training data
    output_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(output_dir, "training_data.json")
    save_training_data(training_examples, output_path)
    
    print("\nDone!")


if __name__ == "__main__":
    main()
