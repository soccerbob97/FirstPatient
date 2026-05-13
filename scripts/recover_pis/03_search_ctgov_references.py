#!/usr/bin/env python3
"""
Step 3: Check ClinicalTrials.gov results_reference field for PI information.

Some trials have publications listed in the results_reference field that weren't
indexed in PubMed under the NCT number. This script checks that field directly.

ClinicalTrials.gov API v2 provides the ReferencesModule which contains:
- references: List of publications with citation info
- type: "RESULT" for results publications, "BACKGROUND" for background refs
"""

import os
import json
import time
from datetime import datetime
from typing import Optional
import requests
from dotenv import load_dotenv

load_dotenv()

# ClinicalTrials.gov API v2
CT_API_BASE = "https://clinicaltrials.gov/api/v2/studies"

# Output directory
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


def get_results_references(nct_id: str) -> list[dict]:
    """
    Fetch results_reference from ClinicalTrials.gov API v2.
    
    Returns list of result publications with citation info.
    """
    url = f"{CT_API_BASE}/{nct_id}"
    params = {
        "format": "json",
        "fields": "ReferencesModule,ContactsLocationsModule",
    }
    
    try:
        response = requests.get(url, params=params, timeout=30)
        
        if response.status_code == 404:
            return []
        
        response.raise_for_status()
        data = response.json()
        
        protocol = data.get("protocolSection", {})
        refs_module = protocol.get("referencesModule", {})
        references = refs_module.get("references", [])
        
        # Filter for results references (not background)
        result_refs = [r for r in references if r.get("type") == "RESULT"]
        
        # Also check for overall officials (investigators)
        contacts_module = protocol.get("contactsLocationsModule", {})
        officials = contacts_module.get("overallOfficials", [])
        
        return {
            "result_references": result_refs,
            "overall_officials": officials,
        }
        
    except Exception as e:
        print(f"    Error fetching {nct_id}: {e}")
        return {"result_references": [], "overall_officials": []}


def parse_citation_for_author(citation: str) -> Optional[dict]:
    """
    Parse a citation string to extract the first author.
    
    Citations are typically in format:
    "Smith J, Jones M, et al. Title. Journal. Year;..."
    """
    if not citation:
        return None
    
    # Try to extract first author (before first comma or "et al")
    parts = citation.split(",")
    if not parts:
        return None
    
    first_part = parts[0].strip()
    
    # Check if it looks like an author name
    # Authors typically have format "LastName Initials" or "LastName AB"
    words = first_part.split()
    if len(words) >= 1:
        # Assume first word is last name
        last_name = words[0]
        initials = words[1] if len(words) > 1 else ""
        
        # Skip if it looks like a title word
        skip_words = ["the", "a", "an", "effect", "efficacy", "safety", "study", "trial"]
        if last_name.lower() in skip_words:
            return None
        
        return {
            "last_name": last_name,
            "initials": initials,
            "full_name": first_part,
        }
    
    return None


def find_pi_from_ctgov_refs(nct_id: str) -> Optional[dict]:
    """
    Find PI for a trial from ClinicalTrials.gov references or officials.
    """
    data = get_results_references(nct_id)
    
    # First check if there are overall officials we missed
    officials = data.get("overall_officials", [])
    for official in officials:
        name = official.get("name")
        role = official.get("role")
        affiliation = official.get("affiliation")
        
        if name and role in ["PRINCIPAL_INVESTIGATOR", "STUDY_DIRECTOR"]:
            return {
                "nct_id": nct_id,
                "pi_name": name,
                "pi_affiliation": affiliation,
                "pi_role": role,
                "source": "ctgov_officials",
            }
    
    # Then check result references
    result_refs = data.get("result_references", [])
    for ref in result_refs:
        citation = ref.get("citation", "")
        pmid = ref.get("pmid")
        
        author = parse_citation_for_author(citation)
        if author:
            return {
                "nct_id": nct_id,
                "pi_name": author["full_name"],
                "pi_last_name": author.get("last_name"),
                "source": "ctgov_results_reference",
                "pmid": pmid,
                "citation": citation[:200],  # Truncate
            }
    
    return None


def main():
    """Main function to search ClinicalTrials.gov references."""
    
    print("=" * 60)
    print("PI Recovery - Step 3: Check ClinicalTrials.gov References")
    print("=" * 60)
    print()
    
    # Load trials still needing PI
    input_file = os.path.join(OUTPUT_DIR, "trials_still_need_pi.json")
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found")
        print("Run 02_search_pubmed.py first")
        return
    
    with open(input_file) as f:
        data = json.load(f)
    
    trials = data.get("trials", [])
    print(f"Loaded {len(trials)} trials still needing PI")
    print()
    
    # Search ClinicalTrials.gov for each trial
    recovered_pis = []
    not_found = []
    
    for i, trial in enumerate(trials):
        nct_id = trial["nct_id"]
        
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(trials)} ({len(recovered_pis)} PIs found)")
        
        result = find_pi_from_ctgov_refs(nct_id)
        
        if result:
            result["trial_title"] = trial.get("title")
            result["trial_status"] = trial.get("status")
            recovered_pis.append(result)
            print(f"  ✓ {nct_id}: {result['pi_name']} (via {result['source']})")
        else:
            not_found.append(trial)
        
        # Rate limiting (be nice to the API)
        time.sleep(0.1)
    
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Trials searched: {len(trials)}")
    print(f"PIs found via ClinicalTrials.gov: {len(recovered_pis)} ({100*len(recovered_pis)/max(len(trials),1):.1f}%)")
    print(f"Still not found: {len(not_found)}")
    print()
    
    # Save results
    output_file = os.path.join(OUTPUT_DIR, "recovered_pis_ctgov.json")
    with open(output_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "source": "ctgov_references",
            "total_searched": len(trials),
            "total_found": len(recovered_pis),
            "pis": recovered_pis,
        }, f, indent=2)
    
    print(f"Saved recovered PIs to: {output_file}")
    
    # Save trials still needing PI
    final_not_found_file = os.path.join(OUTPUT_DIR, "trials_no_pi_found.json")
    with open(final_not_found_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "count": len(not_found),
            "trials": not_found,
        }, f, indent=2)
    
    print(f"Saved trials with no PI found to: {final_not_found_file}")
    print()
    print("Next step: Run 04_import_recovered_pis.py to import into database")


if __name__ == "__main__":
    main()
