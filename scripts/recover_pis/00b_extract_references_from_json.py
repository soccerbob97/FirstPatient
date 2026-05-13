#!/usr/bin/env python3
"""
Extract references from ctg-studies_full.json for trials without PIs.

This script:
1. Loads the list of trials without PIs
2. Streams through the full JSON to find references for those trials
3. Extracts PI candidates from result publications

This avoids making API calls since we already have the data locally.
"""

import os
import json
import ijson
import re
from datetime import datetime
from collections import defaultdict

# Input files
CTG_FILE = "/Users/harshakaranth/Harsha/Projects/ClinicalTrialProject/ctg-studies_full.json"
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


def parse_citation_for_author(citation: str) -> dict | None:
    """
    Parse a citation string to extract the first author.
    
    Citations are typically in format:
    "Smith J, Jones M, et al. Title. Journal. Year;..."
    or
    "Smith JA, Jones MB. Title..."
    """
    if not citation:
        return None
    
    # Try to extract first author (before first comma or period)
    # Common patterns:
    # "LastName AB, ..." or "LastName A, ..." or "LastName AB."
    
    # Split on common delimiters
    parts = re.split(r'[,.]', citation)
    if not parts:
        return None
    
    first_part = parts[0].strip()
    
    # Skip if it looks like a title (starts with common title words)
    skip_patterns = [
        r'^(the|a|an|effect|efficacy|safety|study|trial|randomized|double|single|phase|open|multi)',
        r'^\d',  # Starts with number
        r'^[a-z]',  # Starts with lowercase (likely title)
    ]
    
    for pattern in skip_patterns:
        if re.match(pattern, first_part, re.IGNORECASE):
            return None
    
    # Check if it looks like an author name (has initials or short second word)
    words = first_part.split()
    if len(words) >= 1:
        last_name = words[0]
        
        # Last name should be capitalized and reasonable length
        if not last_name[0].isupper() or len(last_name) < 2:
            return None
        
        # Get initials if present
        initials = ""
        if len(words) > 1:
            # Check if second part looks like initials (1-3 uppercase letters)
            potential_initials = words[1]
            if len(potential_initials) <= 3 and potential_initials.isupper():
                initials = potential_initials
            elif len(potential_initials) <= 3:
                initials = potential_initials.upper()
        
        return {
            "last_name": last_name,
            "initials": initials,
            "full_name": first_part,
            "raw_citation": citation[:200],
        }
    
    return None


def extract_pi_from_study(study: dict, nct_ids_to_find: set) -> dict | None:
    """
    Extract PI information from a study's references.
    
    Returns PI info if found, None otherwise.
    """
    protocol = study.get("protocolSection", {})
    nct_id = protocol.get("identificationModule", {}).get("nctId")
    
    if not nct_id or nct_id not in nct_ids_to_find:
        return None
    
    # Check referencesModule for result publications
    refs_module = protocol.get("referencesModule", {})
    references = refs_module.get("references", [])
    
    # Filter for RESULT type references
    result_refs = [r for r in references if r.get("type") == "RESULT"]
    
    if not result_refs:
        return None
    
    # Try to extract author from first result reference
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
                "citation": citation[:300],
                "total_result_refs": len(result_refs),
            }
    
    return None


def main():
    print("=" * 60)
    print("Extract References from ctg-studies_full.json")
    print("=" * 60)
    print()
    
    # Load list of trials without PIs
    trials_file = os.path.join(OUTPUT_DIR, "trials_without_pi_from_json.json")
    
    if not os.path.exists(trials_file):
        print(f"Error: {trials_file} not found")
        print("Run 00_analyze_ctg_json.py first")
        return
    
    with open(trials_file) as f:
        data = json.load(f)
    
    trials_without_pi = data.get("trials", [])
    nct_ids_to_find = {t["nct_id"] for t in trials_without_pi}
    
    print(f"Trials without PI: {len(nct_ids_to_find):,}")
    print()
    
    # Stream through JSON and extract references
    print("Streaming through JSON file to extract references...")
    print()
    
    recovered_pis = []
    trials_with_refs_no_author = []
    processed = 0
    
    with open(CTG_FILE, "rb") as f:
        studies = ijson.items(f, "item")
        
        for study in studies:
            processed += 1
            
            result = extract_pi_from_study(study, nct_ids_to_find)
            
            if result:
                recovered_pis.append(result)
            
            if processed % 100000 == 0:
                print(f"  Processed {processed:,} studies... ({len(recovered_pis):,} PIs found)")
    
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Trials without PI: {len(nct_ids_to_find):,}")
    print(f"PIs found from references: {len(recovered_pis):,} ({100*len(recovered_pis)/len(nct_ids_to_find):.1f}%)")
    print()
    
    if recovered_pis:
        print("Sample of recovered PIs:")
        for pi in recovered_pis[:5]:
            print(f"  - {pi['nct_id']}: {pi['pi_name']}")
            print(f"    Citation: {pi['citation'][:80]}...")
            print()
    
    # Save results
    output_file = os.path.join(OUTPUT_DIR, "recovered_pis_from_json_refs.json")
    with open(output_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "source": "ctgov_json_references",
            "total_without_pi": len(nct_ids_to_find),
            "total_found": len(recovered_pis),
            "pis": recovered_pis,
        }, f, indent=2)
    
    print(f"Saved {len(recovered_pis):,} recovered PIs to: {output_file}")
    
    # Update the list of trials still needing PI
    found_nct_ids = {pi["nct_id"] for pi in recovered_pis}
    still_need_pi = [t for t in trials_without_pi if t["nct_id"] not in found_nct_ids]
    
    still_need_file = os.path.join(OUTPUT_DIR, "trials_still_need_pi_after_refs.json")
    with open(still_need_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "count": len(still_need_pi),
            "trials": still_need_pi,
        }, f, indent=2)
    
    print(f"Saved {len(still_need_pi):,} trials still needing PI to: {still_need_file}")
    print()
    print("Next: Run 02_search_pubmed.py on the remaining trials")


if __name__ == "__main__":
    main()
