#!/usr/bin/env python3
"""
Test PubMed search on a small sample of trials without PIs.

This script tests the PI recovery pipeline on 50 trials to verify:
1. PubMed API is working
2. We can find publications for NCT numbers
3. We can extract author information

Run this before the full 85K trial search.
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

# Sample size
SAMPLE_SIZE = 50


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
        print(f"    Error searching PubMed for {nct_id}: {e}")
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
        print(f"    Error fetching article details: {e}")
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
        "total_articles_found": len(articles),
    }


def main():
    print("=" * 60)
    print("PI Recovery - Test PubMed Search on Sample")
    print("=" * 60)
    print()
    
    if PUBMED_API_KEY:
        print(f"✓ Using PubMed API key (10 req/sec)")
    else:
        print("⚠ No PubMed API key found (3 req/sec)")
        print("  Get a free key from: https://www.ncbi.nlm.nih.gov/account/")
    print()
    
    # Load trials
    input_file = os.path.join(OUTPUT_DIR, "trials_without_pi_from_json.json")
    
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found")
        print("Run 00_analyze_ctg_json.py first")
        return
    
    with open(input_file) as f:
        data = json.load(f)
    
    all_trials = data.get("trials", [])
    print(f"Total trials without PI: {len(all_trials):,}")
    
    # Filter for COMPLETED trials (more likely to have publications)
    completed_trials = [t for t in all_trials if t.get("status") == "COMPLETED"]
    print(f"Completed trials: {len(completed_trials):,}")
    print()
    
    # Take sample from completed trials
    sample = completed_trials[:SAMPLE_SIZE]
    print(f"Testing on {len(sample)} completed trials...")
    print()
    
    # Search PubMed
    recovered = []
    not_found = []
    
    for i, trial in enumerate(sample):
        nct_id = trial["nct_id"]
        
        result = find_pi_from_pubmed(nct_id)
        
        if result:
            result["trial_title"] = trial.get("title")
            result["trial_status"] = trial.get("status")
            recovered.append(result)
            print(f"  ✓ {nct_id}: {result['pi_name']} ({result['total_articles_found']} articles)")
        else:
            not_found.append(trial)
            print(f"  ✗ {nct_id}: No publication found")
        
        time.sleep(REQUEST_DELAY)
    
    print()
    print("=" * 60)
    print("TEST RESULTS")
    print("=" * 60)
    print(f"Sample size: {len(sample)}")
    print(f"PIs found: {len(recovered)} ({100*len(recovered)/len(sample):.1f}%)")
    print(f"Not found: {len(not_found)}")
    print()
    
    if recovered:
        print("Sample of recovered PIs:")
        for pi in recovered[:5]:
            print(f"  - {pi['nct_id']}: {pi['pi_name']}")
            print(f"    Publication: {pi['publication_title'][:60]}...")
            print(f"    Affiliation: {pi.get('pi_affiliation', 'N/A')[:60]}...")
            print()
    
    # Estimate for full dataset
    recovery_rate = len(recovered) / len(sample)
    estimated_recoverable = int(len(completed_trials) * recovery_rate)
    print(f"Estimated recoverable from completed trials: ~{estimated_recoverable:,}")
    print()
    
    # Save test results
    output_file = os.path.join(OUTPUT_DIR, "test_pubmed_results.json")
    with open(output_file, "w") as f:
        json.dump({
            "generated_at": datetime.now().isoformat(),
            "sample_size": len(sample),
            "found": len(recovered),
            "not_found": len(not_found),
            "recovery_rate": recovery_rate,
            "recovered_pis": recovered,
        }, f, indent=2)
    
    print(f"Saved test results to: {output_file}")


if __name__ == "__main__":
    main()
