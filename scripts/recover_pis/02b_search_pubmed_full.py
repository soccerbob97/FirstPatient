#!/usr/bin/env python3
"""
Full PubMed search for all trials without PIs.

This script searches PubMed for publications linked to NCT numbers
for all 85K trials without PIs. It saves progress periodically
so it can be resumed if interrupted.

Expected runtime: ~8 hours at 3 req/sec (no API key)
                  ~2.5 hours at 10 req/sec (with API key)

Get a free PubMed API key from: https://www.ncbi.nlm.nih.gov/account/
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
PUBMED_API_KEY = os.getenv("PUBMED_API_KEY")
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Rate limiting
REQUESTS_PER_SECOND = 10 if PUBMED_API_KEY else 3
REQUEST_DELAY = 1.0 / REQUESTS_PER_SECOND

# Output directory
OUTPUT_DIR = os.path.dirname(os.path.abspath(__file__))

# Progress save interval
SAVE_INTERVAL = 500  # Save every 500 trials


def search_pubmed_for_nct(nct_id: str) -> list[str]:
    """Search PubMed for articles mentioning the NCT number."""
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
        return []


def fetch_article_details(pmids: list[str]) -> list[dict]:
    """Fetch article details from PubMed for given PMIDs."""
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
        
        root = ET.fromstring(response.content)
        articles = []
        
        for article in root.findall(".//PubmedArticle"):
            pmid = article.findtext(".//PMID")
            title = article.findtext(".//ArticleTitle")
            
            authors = []
            for author in article.findall(".//Author"):
                last_name = author.findtext("LastName") or ""
                fore_name = author.findtext("ForeName") or ""
                affiliation = author.findtext(".//Affiliation") or ""
                
                if last_name:
                    authors.append({
                        "last_name": last_name,
                        "fore_name": fore_name,
                        "full_name": f"{fore_name} {last_name}".strip(),
                        "affiliation": affiliation,
                    })
            
            pub_date = article.find(".//PubDate")
            year = pub_date.findtext("Year") if pub_date is not None else None
            
            articles.append({
                "pmid": pmid,
                "title": title,
                "year": year,
                "authors": authors,
                "first_author": authors[0] if authors else None,
            })
        
        return articles
        
    except Exception as e:
        return []


def find_pi_from_pubmed(nct_id: str) -> Optional[dict]:
    """Find PI for a trial by searching PubMed."""
    pmids = search_pubmed_for_nct(nct_id)
    
    if not pmids:
        return None
    
    time.sleep(REQUEST_DELAY)
    
    articles = fetch_article_details(pmids)
    
    if not articles:
        return None
    
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


def load_progress() -> tuple[list, set, int]:
    """Load progress from previous run if exists."""
    progress_file = os.path.join(OUTPUT_DIR, "pubmed_search_progress.json")
    
    if os.path.exists(progress_file):
        with open(progress_file) as f:
            data = json.load(f)
        return (
            data.get("recovered_pis", []),
            set(data.get("processed_nct_ids", [])),
            data.get("last_index", 0)
        )
    
    return [], set(), 0


def save_progress(recovered_pis: list, processed_nct_ids: set, last_index: int):
    """Save progress for resume capability."""
    progress_file = os.path.join(OUTPUT_DIR, "pubmed_search_progress.json")
    
    with open(progress_file, "w") as f:
        json.dump({
            "saved_at": datetime.now().isoformat(),
            "recovered_pis": recovered_pis,
            "processed_nct_ids": list(processed_nct_ids),
            "last_index": last_index,
            "total_found": len(recovered_pis),
        }, f)


def main():
    print("=" * 60)
    print("PI Recovery - Full PubMed Search")
    print("=" * 60)
    print()
    
    if PUBMED_API_KEY:
        print(f"✓ Using PubMed API key (10 req/sec)")
        estimated_time = "~2.5 hours"
    else:
        print("⚠ No PubMed API key found (3 req/sec)")
        print("  Get a free key from: https://www.ncbi.nlm.nih.gov/account/")
        estimated_time = "~8 hours"
    print(f"  Estimated time: {estimated_time}")
    print()
    
    # Load trials
    input_file = os.path.join(OUTPUT_DIR, "trials_without_pi_from_json.json")
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found")
        return
    
    with open(input_file) as f:
        data = json.load(f)
    
    all_trials = data.get("trials", [])
    print(f"Total trials without PI: {len(all_trials):,}")
    
    # Load progress
    recovered_pis, processed_nct_ids, start_index = load_progress()
    
    if start_index > 0:
        print(f"Resuming from index {start_index:,} ({len(recovered_pis):,} PIs found so far)")
    print()
    
    # Process trials
    start_time = datetime.now()
    
    for i, trial in enumerate(all_trials[start_index:], start=start_index):
        nct_id = trial["nct_id"]
        
        # Skip if already processed
        if nct_id in processed_nct_ids:
            continue
        
        # Search PubMed
        result = find_pi_from_pubmed(nct_id)
        
        if result:
            result["trial_title"] = trial.get("title")
            result["trial_status"] = trial.get("status")
            recovered_pis.append(result)
        
        processed_nct_ids.add(nct_id)
        
        # Progress update
        if (i + 1) % 100 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            rate = (i - start_index + 1) / elapsed if elapsed > 0 else 0
            remaining = (len(all_trials) - i - 1) / rate if rate > 0 else 0
            
            print(f"  {i + 1:,}/{len(all_trials):,} | Found: {len(recovered_pis):,} | "
                  f"Rate: {rate:.1f}/sec | ETA: {remaining/3600:.1f}h")
        
        # Save progress periodically
        if (i + 1) % SAVE_INTERVAL == 0:
            save_progress(recovered_pis, processed_nct_ids, i + 1)
        
        time.sleep(REQUEST_DELAY)
    
    # Final save
    save_progress(recovered_pis, processed_nct_ids, len(all_trials))
    
    print()
    print("=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print(f"Total trials searched: {len(all_trials):,}")
    print(f"PIs found: {len(recovered_pis):,} ({100*len(recovered_pis)/len(all_trials):.1f}%)")
    print()
    
    # Save final results
    output_file = os.path.join(OUTPUT_DIR, "recovered_pis_pubmed_full.json")
    with open(output_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "source": "pubmed",
            "total_searched": len(all_trials),
            "total_found": len(recovered_pis),
            "pis": recovered_pis,
        }, f, indent=2)
    
    print(f"Saved results to: {output_file}")
    print()
    print("Next step: Run 04_import_recovered_pis.py to import into database")


if __name__ == "__main__":
    main()
