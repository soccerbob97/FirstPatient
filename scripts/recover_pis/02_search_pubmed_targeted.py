#!/usr/bin/env python3
"""
Step 2: Search PubMed for PIs of oncology/obesity trials.

Searches PubMed for publications linked to NCT numbers.
First author of the publication is typically the lead PI.

Expected runtime: ~45 min for 27K trials (with API key at 10 req/sec)
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

# Config
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FILE = os.path.join(SCRIPT_DIR, "oncology_obesity_without_pi.json")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "recovered_pis_oncology_obesity.json")
PROGRESS_FILE = os.path.join(SCRIPT_DIR, "pubmed_progress_targeted.json")

# PubMed API
PUBMED_API_KEY = os.getenv("PUBMED_API_KEY")
ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# Rate limiting
REQUESTS_PER_SECOND = 10 if PUBMED_API_KEY else 3
REQUEST_DELAY = 1.0 / REQUESTS_PER_SECOND

# Progress save interval
SAVE_INTERVAL = 200


def search_pubmed_for_nct(nct_id: str) -> list[str]:
    """Search PubMed for articles mentioning the NCT number."""
    params = {
        "db": "pubmed",
        "term": f"{nct_id}[Secondary Source ID] OR {nct_id}[Title/Abstract]",
        "retmode": "json",
        "retmax": 5,
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
    """Fetch article details from PubMed."""
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
    except Exception:
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
    """Load progress from previous run."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE) as f:
            data = json.load(f)
        return (
            data.get("recovered_pis", []),
            set(data.get("processed_nct_ids", [])),
            data.get("last_index", 0)
        )
    return [], set(), 0


def save_progress(recovered_pis: list, processed_nct_ids: set, last_index: int):
    """Save progress for resume."""
    with open(PROGRESS_FILE, "w") as f:
        json.dump({
            "saved_at": datetime.now().isoformat(),
            "recovered_pis": recovered_pis,
            "processed_nct_ids": list(processed_nct_ids),
            "last_index": last_index,
            "total_found": len(recovered_pis),
        }, f)


def main():
    print("=" * 60)
    print("PI RECOVERY - PubMed Search (Oncology + Obesity)")
    print("=" * 60)
    print()
    
    if PUBMED_API_KEY:
        print("✓ Using PubMed API key (10 req/sec)")
    else:
        print("⚠ No API key - using 3 req/sec (slower)")
    print()
    
    # Load input
    if not os.path.exists(INPUT_FILE):
        print(f"Error: {INPUT_FILE} not found")
        print("Run 01_extract_oncology_obesity.py first")
        return
    
    with open(INPUT_FILE) as f:
        data = json.load(f)
    
    trials = data.get("trials", [])
    print(f"Trials to search: {len(trials):,}")
    
    # Load progress
    recovered_pis, processed_nct_ids, start_index = load_progress()
    if start_index > 0:
        print(f"Resuming from index {start_index:,} ({len(recovered_pis):,} PIs found)")
    
    estimated_time = (len(trials) - start_index) / REQUESTS_PER_SECOND / 60
    print(f"Estimated time: ~{estimated_time:.0f} minutes")
    print()
    
    # Process
    start_time = datetime.now()
    
    for i, trial in enumerate(trials[start_index:], start=start_index):
        nct_id = trial["nct_id"]
        
        if nct_id in processed_nct_ids:
            continue
        
        result = find_pi_from_pubmed(nct_id)
        
        if result:
            result["trial_title"] = trial.get("title")
            result["trial_status"] = trial.get("status")
            result["conditions"] = trial.get("conditions")
            recovered_pis.append(result)
        
        processed_nct_ids.add(nct_id)
        
        # Progress update
        if (i + 1) % 100 == 0:
            elapsed = (datetime.now() - start_time).total_seconds()
            processed = i - start_index + 1
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = (len(trials) - i - 1) / rate / 60 if rate > 0 else 0
            pct = 100 * len(recovered_pis) / (i + 1)
            
            print(f"  {i + 1:,}/{len(trials):,} | Found: {len(recovered_pis):,} ({pct:.1f}%) | ETA: {remaining:.0f}m")
        
        # Save progress
        if (i + 1) % SAVE_INTERVAL == 0:
            save_progress(recovered_pis, processed_nct_ids, i + 1)
        
        time.sleep(REQUEST_DELAY)
    
    # Final save
    save_progress(recovered_pis, processed_nct_ids, len(trials))
    
    print()
    print("=" * 60)
    print("COMPLETE")
    print("=" * 60)
    print(f"Trials searched: {len(trials):,}")
    print(f"PIs found: {len(recovered_pis):,} ({100*len(recovered_pis)/len(trials):.1f}%)")
    print()
    
    # Save final results
    with open(OUTPUT_FILE, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "source": "pubmed",
            "total_searched": len(trials),
            "total_found": len(recovered_pis),
            "pis": recovered_pis,
        }, f, indent=2)
    
    print(f"Saved to: {OUTPUT_FILE}")
    print()
    print("Next step: Run 03_import_recovered_pis.py")


if __name__ == "__main__":
    main()
