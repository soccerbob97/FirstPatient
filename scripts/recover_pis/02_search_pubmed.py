#!/usr/bin/env python3
"""
Step 2: Search PubMed for publications linked to NCT numbers.

For each trial without a PI, search PubMed for publications that mention the NCT number.
The first author of the publication is typically the lead PI.

Uses PubMed E-utilities API:
- esearch: Find PMIDs for NCT number
- efetch: Get article details including authors

Rate limits:
- Without API key: 3 requests/second
- With API key: 10 requests/second (get free key from NCBI)
"""

import os
import json
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional
import requests
from dotenv import load_dotenv

load_dotenv()

# PubMed E-utilities
PUBMED_API_KEY = os.getenv("PUBMED_API_KEY")  # Optional but recommended
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Rate limiting
REQUESTS_PER_SECOND = 10 if PUBMED_API_KEY else 3
REQUEST_DELAY = 1.0 / REQUESTS_PER_SECOND

# Output directory
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))


def search_pubmed_for_nct(nct_id: str) -> list[str]:
    """
    Search PubMed for articles mentioning the NCT number.
    
    Returns list of PMIDs.
    """
    params = {
        "db": "pubmed",
        "term": f"{nct_id}[Secondary Source ID] OR {nct_id}[Title/Abstract]",
        "retmode": "json",
        "retmax": 10,
    }
    
    if PUBMED_API_KEY:
        params["api_key"] = PUBMED_API_KEY
    
    try:
        response = requests.get(ESEARCH_URL, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data.get("esearchresult", {}).get("idlist", [])
    except Exception as e:
        print(f"    Error searching PubMed for {nct_id}: {e}")
        return []


def fetch_article_details(pmids: list[str]) -> list[dict]:
    """
    Fetch article details from PubMed for given PMIDs.
    
    Returns list of article info including authors.
    """
    if not pmids:
        return []
    
    params = {
        "db": "pubmed",
        "id": ",".join(pmids),
        "retmode": "xml",
    }
    
    if PUBMED_API_KEY:
        params["api_key"] = PUBMED_API_KEY
    
    try:
        response = requests.get(EFETCH_URL, params=params, timeout=30)
        response.raise_for_status()
        
        # Parse XML response
        root = ET.fromstring(response.content)
        articles = []
        
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//PMID")
            title = article.findtext(".//ArticleTitle")
            
            # Get authors
            authors = []
            for author in article.findall(".//Author"):
                last_name = author.findtext("LastName") or ""
                fore_name = author.findtext("ForeName") or ""
                initials = author.findtext("Initials") or ""
                
                # Get affiliation
                affiliation = author.findtext(".//Affiliation") or ""
                
                if last_name:
                    authors.append({
                        "last_name": last_name,
                        "fore_name": fore_name,
                        "initials": initials,
                        "full_name": f"{fore_name} {last_name}".strip(),
                        "affiliation": affiliation,
                    })
            
            # Get publication date
            pub_date = article.find(".//PubDate")
            year = pub_date.findtext("Year") if pub_date is not None else None
            
            articles.append({
                "pmid": pmid,
                "title": title,
                "year": year,
                "authors": authors,
                "first_author": authors[0] if authors else None,
                "last_author": authors[-1] if authors else None,
            })
        
        return articles
        
    except Exception as e:
        print(f"    Error fetching article details: {e}")
        return []


def find_pi_from_pubmed(nct_id: str) -> Optional[dict]:
    """
    Find PI for a trial by searching PubMed for linked publications.
    
    The first author of the primary results publication is typically the lead PI.
    """
    # Search for articles
    pmids = search_pubmed_for_nct(nct_id)
    
    if not pmids:
        return None
    
    time.sleep(REQUEST_DELAY)
    
    # Fetch article details
    articles = fetch_article_details(pmids)
    
    if not articles:
        return None
    
    # Use first article's first author as PI
    # (Could be improved by looking for "results" publications specifically)
    best_article = articles[0]
    first_author = best_article.get("first_author")
    
    if not first_author:
        return None
    
    return {
        "nct_id": nct_id,
        "pi_name": first_author["full_name"],
        "pi_last_name": first_author["last_name"],
        "pi_first_name": first_author["fore_name"],
        "pi_affiliation": first_author.get("affiliation"),
        "source": "pubmed",
        "pmid": best_article["pmid"],
        "publication_title": best_article["title"],
        "publication_year": best_article["year"],
    }


def main():
    """Main function to search PubMed for PIs."""
    
    print("=" * 60)
    print("PI Recovery - Step 2: Search PubMed for Publications")
    print("=" * 60)
    print()
    
    if PUBMED_API_KEY:
        print(f"Using PubMed API key (10 req/sec)")
    else:
        print("No PubMed API key found (3 req/sec)")
        print("Get a free key from: https://www.ncbi.nlm.nih.gov/account/")
    print()
    
    # Load trials to recover - prefer the JSON analysis output
    input_file = os.path.join(OUTPUT_DIR, "trials_without_pi_from_json.json")
    
    if not os.path.exists(input_file):
        # Fallback to API-fetched file
        input_file = os.path.join(OUTPUT_DIR, "trials_to_recover.json")
    
    if not os.path.exists(input_file):
        print(f"Error: No input file found")
        print("Run 00_analyze_ctg_json.py or 01_fetch_trials_without_pi.py first")
        return
    
    print(f"Loading trials from: {input_file}")
    with open(input_file) as f:
        data = json.load(f)
    
    trials = data.get("trials", [])
    print(f"Loaded {len(trials)} trials to search")
    print()
    
    # Search PubMed for each trial
    recovered_pis = []
    not_found = []
    
    for i, trial in enumerate(trials):
        nct_id = trial["nct_id"]
        
        if (i + 1) % 100 == 0:
            print(f"Progress: {i + 1}/{len(trials)} ({len(recovered_pis)} PIs found)")
        
        result = find_pi_from_pubmed(nct_id)
        
        if result:
            result["trial_title"] = trial.get("title")
            result["trial_status"] = trial.get("status")
            recovered_pis.append(result)
            print(f"  ✓ {nct_id}: {result['pi_name']}")
        else:
            not_found.append(trial)
        
        time.sleep(REQUEST_DELAY)
    
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Trials searched: {len(trials)}")
    print(f"PIs found via PubMed: {len(recovered_pis)} ({100*len(recovered_pis)/len(trials):.1f}%)")
    print(f"Not found: {len(not_found)}")
    print()
    
    # Save results
    output_file = os.path.join(OUTPUT_DIR, "recovered_pis_pubmed.json")
    with open(output_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "source": "pubmed",
            "total_searched": len(trials),
            "total_found": len(recovered_pis),
            "pis": recovered_pis,
        }, f, indent=2)
    
    print(f"Saved recovered PIs to: {output_file}")
    
    # Save trials still needing PI
    not_found_file = os.path.join(OUTPUT_DIR, "trials_still_need_pi.json")
    with open(not_found_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "count": len(not_found),
            "trials": not_found,
        }, f, indent=2)
    
    print(f"Saved trials still needing PI to: {not_found_file}")
    print()
    print("Next step: Run 03_search_ctgov_references.py for trials not found in PubMed")


if __name__ == "__main__":
    main()
