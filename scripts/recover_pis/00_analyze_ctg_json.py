#!/usr/bin/env python3
"""
Analyze the ctg-studies_full.json file to identify trials without PIs.

This script streams through the large JSON file to:
1. Count total trials
2. Identify trials WITH investigators (overallOfficials or responsibleParty)
3. Identify trials WITHOUT investigators (candidates for PI recovery)
4. Save the NCT IDs of trials without PIs for recovery

The file is ~9GB so we use ijson for streaming JSON parsing.
"""

import os
import json
import ijson
from datetime import datetime
from collections import defaultdict

# Input file
CTG_FILE = "/Users/harshakaranth/Harsha/Projects/ClinicalTrialProject/ctg-studies_full.json"

# Output directory
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


def has_investigator(study: dict) -> tuple[bool, str]:
    """
    Check if a study has investigator information.
    
    Returns (has_pi, source) where source indicates where PI was found.
    """
    protocol = study.get("protocolSection", {})
    
    # Check 1: overallOfficials in contactsLocationsModule
    contacts_module = protocol.get("contactsLocationsModule", {})
    overall_officials = contacts_module.get("overallOfficials", [])
    
    for official in overall_officials:
        name = official.get("name", "")
        role = official.get("role", "")
        if name and role in ["PRINCIPAL_INVESTIGATOR", "STUDY_DIRECTOR"]:
            return True, "overallOfficials"
    
    # Check 2: responsibleParty in sponsorCollaboratorsModule
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    responsible_party = sponsor_module.get("responsibleParty", {})
    
    if responsible_party.get("investigatorFullName"):
        return True, "responsibleParty"
    
    # Check 3: Any official with a name (even if role is not PI)
    for official in overall_officials:
        if official.get("name"):
            return True, "overallOfficials_other"
    
    return False, None


def extract_study_info(study: dict) -> dict:
    """Extract key info from a study for saving."""
    protocol = study.get("protocolSection", {})
    id_module = protocol.get("identificationModule", {})
    status_module = protocol.get("statusModule", {})
    conditions_module = protocol.get("conditionsModule", {})
    design_module = protocol.get("designModule", {})
    
    return {
        "nct_id": id_module.get("nctId"),
        "title": id_module.get("briefTitle"),
        "status": status_module.get("overallStatus"),
        "conditions": conditions_module.get("conditions", []),
        "phase": design_module.get("phases", []),
        "start_date": status_module.get("startDateStruct", {}).get("date"),
        "completion_date": status_module.get("completionDateStruct", {}).get("date"),
    }


def main():
    print("=" * 60)
    print("Analyzing ctg-studies_full.json for trials without PIs")
    print("=" * 60)
    print()
    print(f"Input file: {CTG_FILE}")
    print(f"File size: {os.path.getsize(CTG_FILE) / (1024**3):.2f} GB")
    print()
    
    # Counters
    total_studies = 0
    with_pi = 0
    without_pi = 0
    pi_sources = defaultdict(int)
    status_counts = defaultdict(int)
    
    # Lists to save
    trials_without_pi = []
    trials_with_pi_sample = []  # Sample of trials with PI for reference
    
    print("Streaming through JSON file...")
    print()
    
    with open(CTG_FILE, "rb") as f:
        # ijson parses the JSON array item by item
        studies = ijson.items(f, "item")
        
        for study in studies:
            total_studies += 1
            
            has_pi, source = has_investigator(study)
            study_info = extract_study_info(study)
            status = study_info.get("status", "UNKNOWN")
            status_counts[status] += 1
            
            if has_pi:
                with_pi += 1
                pi_sources[source] += 1
                
                # Save sample of trials with PI
                if len(trials_with_pi_sample) < 100:
                    trials_with_pi_sample.append(study_info)
            else:
                without_pi += 1
                trials_without_pi.append(study_info)
            
            # Progress update
            if total_studies % 50000 == 0:
                print(f"  Processed {total_studies:,} studies... ({with_pi:,} with PI, {without_pi:,} without)")
    
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total studies: {total_studies:,}")
    print(f"Studies WITH PI: {with_pi:,} ({100*with_pi/total_studies:.1f}%)")
    print(f"Studies WITHOUT PI: {without_pi:,} ({100*without_pi/total_studies:.1f}%)")
    print()
    
    print("PI Sources:")
    for source, count in sorted(pi_sources.items(), key=lambda x: -x[1]):
        print(f"  {source}: {count:,}")
    print()
    
    print("Status Distribution (without PI):")
    status_without_pi = defaultdict(int)
    for trial in trials_without_pi:
        status_without_pi[trial.get("status", "UNKNOWN")] += 1
    for status, count in sorted(status_without_pi.items(), key=lambda x: -x[1])[:10]:
        print(f"  {status}: {count:,}")
    print()
    
    # Save trials without PI
    output_file = os.path.join(OUTPUT_DIR, "trials_without_pi_from_json.json")
    with open(output_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "source_file": CTG_FILE,
            "total_studies": total_studies,
            "with_pi": with_pi,
            "without_pi": without_pi,
            "trials": trials_without_pi,
        }, f, indent=2)
    
    print(f"Saved {len(trials_without_pi):,} trials without PI to:")
    print(f"  {output_file}")
    print()
    
    # Save summary stats
    stats_file = os.path.join(OUTPUT_DIR, "ctg_analysis_stats.json")
    with open(stats_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "total_studies": total_studies,
            "with_pi": with_pi,
            "without_pi": without_pi,
            "pi_sources": dict(pi_sources),
            "status_counts": dict(status_counts),
            "status_without_pi": dict(status_without_pi),
        }, f, indent=2)
    
    print(f"Saved stats to: {stats_file}")
    print()
    print("Next step: Run 02_search_pubmed.py to find PIs for these trials")
    print("(Update the input file path in that script first)")


if __name__ == "__main__":
    main()
