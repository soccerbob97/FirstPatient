#!/usr/bin/env python3
"""
ORCID + Semantic Scholar Investigator Enrichment Script

Enriches investigators table with publication data using a two-step approach:
1. ORCID lookup (high confidence) - search by name + affiliation
2. Semantic Scholar lookup - via ORCID ID or name search fallback

Data enriched:
- orcid_id, semantic_scholar_id
- h-index, paper count, citation count
- Research areas extracted from publications
- Notable papers for tool calling

Usage:
    PYTHONPATH=. python scripts/enrich_investigators_s2.py --limit 10000
    PYTHONPATH=. python scripts/enrich_investigators_s2.py --resume --limit 50000
    PYTHONPATH=. python scripts/enrich_investigators_s2.py --skip-orcid  # S2 only
    
Requirements:
    - SEMANTIC_SCHOLAR_API_KEY in .env
    - ORCID_CLIENT_ID and ORCID_CLIENT_SECRET in .env (optional but recommended)
    - pip install aiohttp rapidfuzz tenacity python-dotenv
"""

import os
import sys
import json
import asyncio
import argparse
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from collections import Counter

import aiohttp
from dotenv import load_dotenv
from rapidfuzz import fuzz
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

# Load environment
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.supabase_client import get_supabase_admin_client
import time

# Configuration
S2_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY")
S2_BASE_URL = "https://api.semanticscholar.org/graph/v1"

ORCID_CLIENT_ID = os.getenv("ORCID_CLIENT_ID")
ORCID_CLIENT_SECRET = os.getenv("ORCID_CLIENT_SECRET")
ORCID_BASE_URL = "https://pub.orcid.org/v3.0"
ORCID_TOKEN_URL = "https://orcid.org/oauth/token"

CHECKPOINT_FILE = "s2_enrichment_checkpoint.json"

# Rate limiting
# S2: 1 req/sec with API key (dedicated), ~10 req/sec without (shared pool)
# ORCID: 24 req/sec for Public API
S2_REQUESTS_PER_SECOND = 1 if S2_API_KEY else 10  # Public API shares 1000 RPS pool
ORCID_REQUESTS_PER_SECOND = 20  # Stay under 24 limit
CONCURRENT_REQUESTS = 1 if S2_API_KEY else 5  # Conservative for public API

# Matching thresholds
MIN_MATCH_CONFIDENCE = 0.65
NAME_WEIGHT = 0.4
AFFILIATION_WEIGHT = 0.6

# Sponsor/org keywords to filter out
SPONSOR_KEYWORDS = [
    'clinical', 'pharma', 'inc', 'llc', 'ltd', 'center', 'centre',
    'transparency', 'trials', 'research group', 'registry', 'gcr',
    'global', 'coordinator', 'gsk', 'glaxo', 'pfizer', 'novartis',
    'merck', 'sanofi', 'astrazeneca', 'roche', 'lilly', 'bristol',
    'johnson', 'abbvie', 'amgen', 'biogen', 'gilead', 'boehringer',
    'bayer', 'takeda', 'novo nordisk', 'regeneron', 'vertex', 'moderna',
]


class OrcidClient:
    """Async client for ORCID Public API."""
    
    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token: Optional[str] = None
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_times = []
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        if self.client_id and self.client_secret:
            await self._get_access_token()
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def _get_access_token(self):
        """Get ORCID access token using client credentials."""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials",
            "scope": "/read-public"
        }
        async with self.session.post(ORCID_TOKEN_URL, data=data) as resp:
            if resp.status == 200:
                result = await resp.json()
                self.access_token = result.get("access_token")
                print(f"✅ ORCID access token obtained")
            else:
                print(f"⚠️  Failed to get ORCID token: {resp.status}")
    
    async def _rate_limit(self):
        """Enforce rate limiting for ORCID."""
        now = asyncio.get_event_loop().time()
        self.request_times = [t for t in self.request_times if now - t < 1.0]
        
        if len(self.request_times) >= ORCID_REQUESTS_PER_SECOND:
            sleep_time = 1.0 - (now - self.request_times[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        
        self.request_times.append(now)
    
    def _parse_name(self, full_name: str) -> tuple[str, str]:
        """Parse full name into given and family names."""
        # Remove credentials
        name = re.sub(r'\b(MD|PhD|Dr|Prof|MBBS|FRCP|M\.D\.|Ph\.D\.|DO|MPH|MS|MA|MBA|RN|NP|PA)\b', '', full_name, flags=re.I)
        name = re.sub(r'[,.]', ' ', name)
        parts = name.split()
        
        if len(parts) >= 2:
            # Assume "First Last" or "Last, First" format
            if ',' in full_name:
                return parts[1] if len(parts) > 1 else "", parts[0]
            return parts[0], parts[-1]
        elif len(parts) == 1:
            return "", parts[0]
        return "", ""
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def search_by_name_affiliation(
        self, 
        full_name: str, 
        affiliation: Optional[str] = None
    ) -> Optional[str]:
        """
        Search ORCID by name and affiliation.
        Returns ORCID ID if found with high confidence, else None.
        """
        if not self.access_token:
            return None
        
        await self._rate_limit()
        
        given_name, family_name = self._parse_name(full_name)
        if not family_name:
            return None
        
        # Build query
        query_parts = [f'family-name:"{family_name}"']
        if given_name:
            query_parts.append(f'given-names:"{given_name}"')
        if affiliation:
            # Take first part of affiliation (before comma)
            clean_aff = affiliation.split(',')[0].strip()
            if len(clean_aff) > 3:
                query_parts.append(f'affiliation-org-name:"{clean_aff}"')
        
        query = " AND ".join(query_parts)
        
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json"
        }
        
        url = f"{ORCID_BASE_URL}/search/"
        params = {"q": query}
        
        try:
            async with self.session.get(url, params=params, headers=headers, timeout=15) as resp:
                if resp.status == 429:
                    await asyncio.sleep(5)
                    raise aiohttp.ClientError("Rate limited")
                
                if resp.status != 200:
                    return None
                
                data = await resp.json()
                num_found = data.get("num-found", 0)
                
                # High confidence: exactly 1 result
                if num_found == 1:
                    result = data.get("result", [{}])[0]
                    orcid_id = result.get("orcid-identifier", {}).get("path")
                    return orcid_id
                
                # Medium confidence: 2-3 results, take first
                if 1 < num_found <= 3:
                    result = data.get("result", [{}])[0]
                    orcid_id = result.get("orcid-identifier", {}).get("path")
                    return orcid_id
                
                return None
        except Exception:
            return None


class SemanticScholarClient:
    """Async client for Semantic Scholar API."""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key
        self.headers = {"x-api-key": api_key} if api_key else {}
        self.session: Optional[aiohttp.ClientSession] = None
        self.request_times = []
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(headers=self.headers)
        return self
    
    async def __aexit__(self, *args):
        if self.session:
            await self.session.close()
    
    async def _rate_limit(self):
        """Enforce rate limiting."""
        now = asyncio.get_event_loop().time()
        # Remove requests older than 1 second
        self.request_times = [t for t in self.request_times if now - t < 1.0]
        
        if len(self.request_times) >= S2_REQUESTS_PER_SECOND:
            sleep_time = 1.0 - (now - self.request_times[0])
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
        
        self.request_times.append(now)
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def get_author_by_orcid(self, orcid_id: str) -> Optional[dict]:
        """Get author details by ORCID ID (high confidence lookup)."""
        await self._rate_limit()
        
        url = f"{S2_BASE_URL}/author/ORCID:{orcid_id}"
        params = {
            "fields": "authorId,name,affiliations,paperCount,citationCount,hIndex,papers.title,papers.citationCount,papers.year,papers.fieldsOfStudy"
        }
        
        async with self.session.get(url, params=params, timeout=15) as resp:
            if resp.status == 429:
                await asyncio.sleep(5)
                raise aiohttp.ClientError("Rate limited")
            
            if resp.status == 404:
                # ORCID not found in S2
                return None
            
            if resp.status != 200:
                return None
            
            return await resp.json()
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def search_author(self, name: str) -> list[dict]:
        """Search for authors by name (fallback method)."""
        await self._rate_limit()
        
        url = f"{S2_BASE_URL}/author/search"
        params = {
            "query": name,
            "fields": "authorId,name,affiliations,paperCount,hIndex,citationCount",
            "limit": 10
        }
        
        async with self.session.get(url, params=params, timeout=15) as resp:
            if resp.status == 429:
                # Rate limited - wait and retry
                await asyncio.sleep(5)
                raise aiohttp.ClientError("Rate limited")
            
            if resp.status != 200:
                return []
            
            data = await resp.json()
            return data.get("data", [])
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((aiohttp.ClientError, asyncio.TimeoutError))
    )
    async def get_author_details(self, author_id: str) -> Optional[dict]:
        """Get detailed author information including papers."""
        await self._rate_limit()
        
        url = f"{S2_BASE_URL}/author/{author_id}"
        params = {
            "fields": "authorId,name,affiliations,paperCount,citationCount,hIndex,papers.title,papers.citationCount,papers.year,papers.fieldsOfStudy"
        }
        
        async with self.session.get(url, params=params, timeout=15) as resp:
            if resp.status == 429:
                await asyncio.sleep(5)
                raise aiohttp.ClientError("Rate limited")
            
            if resp.status != 200:
                return None
            
            return await resp.json()
    
    async def batch_get_authors(self, author_ids: list[str]) -> list[dict]:
        """Batch fetch author details (up to 1000)."""
        if not author_ids:
            return []
        
        await self._rate_limit()
        
        url = f"{S2_BASE_URL}/author/batch"
        params = {
            "fields": "authorId,name,affiliations,paperCount,citationCount,hIndex,papers.title,papers.citationCount,papers.year,papers.fieldsOfStudy"
        }
        
        async with self.session.post(
            url, 
            params=params, 
            json={"ids": author_ids[:1000]},
            timeout=30
        ) as resp:
            if resp.status == 429:
                await asyncio.sleep(5)
                raise aiohttp.ClientError("Rate limited")
            
            if resp.status != 200:
                return []
            
            return await resp.json()


def normalize_name(name: str) -> str:
    """Normalize name for comparison."""
    # Remove credentials
    name = re.sub(r'\b(MD|PhD|Dr|Prof|MBBS|FRCP|M\.D\.|Ph\.D\.|DO|MPH|MS|MA|MBA|RN|NP|PA)\b', '', name, flags=re.I)
    # Remove punctuation
    name = re.sub(r'[^\w\s]', ' ', name)
    # Normalize whitespace
    name = ' '.join(name.split())
    return name.lower().strip()


def is_likely_sponsor(name: str) -> bool:
    """Check if name looks like a sponsor/organization."""
    name_lower = name.lower()
    return any(kw in name_lower for kw in SPONSOR_KEYWORDS)


def match_investigator(
    name: str, 
    affiliation: Optional[str], 
    candidates: list[dict]
) -> tuple[Optional[dict], float]:
    """
    Match CT.gov investigator to Semantic Scholar author.
    Returns (best_match, confidence_score) or (None, 0).
    """
    if not candidates:
        return None, 0
    
    best_match = None
    best_score = 0
    
    normalized_name = normalize_name(name)
    
    for candidate in candidates:
        if not candidate:
            continue
            
        # Name similarity (0-1)
        candidate_name = normalize_name(candidate.get("name", ""))
        name_score = fuzz.ratio(normalized_name, candidate_name) / 100
        
        # Also try token sort ratio for name order differences
        name_score = max(
            name_score,
            fuzz.token_sort_ratio(normalized_name, candidate_name) / 100
        )
        
        # Affiliation similarity (0-1)
        aff_score = 0.5  # Neutral default
        if affiliation and candidate.get("affiliations"):
            aff_scores = [
                fuzz.partial_ratio(affiliation.lower(), aff.lower()) / 100
                for aff in candidate["affiliations"]
                if aff
            ]
            if aff_scores:
                aff_score = max(aff_scores)
        
        # Combined score
        score = NAME_WEIGHT * name_score + AFFILIATION_WEIGHT * aff_score
        
        # Bonus for having publications (more likely to be the right person)
        if candidate.get("paperCount", 0) > 5:
            score += 0.05
        
        if score > best_score:
            best_match = candidate
            best_score = score
    
    # Only return if confidence threshold met
    if best_score >= MIN_MATCH_CONFIDENCE:
        return best_match, round(best_score, 2)
    
    return None, 0


def extract_research_areas(papers: list[dict]) -> list[str]:
    """Extract research areas from paper fields of study."""
    if not papers:
        return []
    
    # Count fields of study
    field_counts = Counter()
    for paper in papers:
        fields = paper.get("fieldsOfStudy") or []
        for field in fields:
            if field:
                field_counts[field] += 1
    
    # Return top 5 most common
    return [field for field, _ in field_counts.most_common(5)]


def extract_notable_papers(papers: list[dict], limit: int = 5) -> list[dict]:
    """Extract top papers by citation count."""
    if not papers:
        return []
    
    # Sort by citations
    sorted_papers = sorted(
        [p for p in papers if p],
        key=lambda p: p.get("citationCount") or 0,
        reverse=True
    )
    
    # Return top N with relevant fields
    return [
        {
            "title": p.get("title", ""),
            "citationCount": p.get("citationCount", 0),
            "year": p.get("year")
        }
        for p in sorted_papers[:limit]
        if p.get("title")
    ]


class Checkpoint:
    """Manage enrichment progress checkpoint."""
    
    def __init__(self, filepath: str = CHECKPOINT_FILE):
        self.filepath = filepath
        self.data = self._load()
    
    def _load(self) -> dict:
        if os.path.exists(self.filepath):
            with open(self.filepath) as f:
                return json.load(f)
        return {
            "last_processed_id": 0,
            "total_processed": 0,
            "total_matched": 0,
            "total_failed": 0,
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
    
    def save(self):
        self.data["updated_at"] = datetime.now().isoformat()
        with open(self.filepath, "w") as f:
            json.dump(self.data, f, indent=2)
    
    def update(self, last_id: int, matched: int, failed: int):
        self.data["last_processed_id"] = last_id
        self.data["total_processed"] += matched + failed
        self.data["total_matched"] += matched
        self.data["total_failed"] += failed
        self.save()


async def enrich_batch(
    s2_client: SemanticScholarClient,
    orcid_client: Optional[OrcidClient],
    supabase,
    investigators: list[dict],
    semaphore: asyncio.Semaphore,
    use_orcid: bool = True
) -> tuple[int, int, int]:
    """
    Enrich a batch of investigators using ORCID + S2.
    Returns (matched_count, failed_count, orcid_matched_count).
    """
    matched = 0
    failed = 0
    orcid_matched = 0
    
    async def process_one(inv: dict) -> tuple[bool, str]:
        """Returns (success, match_source)"""
        async with semaphore:
            try:
                orcid_id = None
                details = None
                match_source = None
                confidence = 0.0
                
                # Step 1: Try ORCID lookup first (high confidence)
                if use_orcid and orcid_client and orcid_client.access_token:
                    orcid_id = await orcid_client.search_by_name_affiliation(
                        inv["full_name"],
                        inv.get("affiliation")
                    )
                    
                    if orcid_id:
                        # Use ORCID to get S2 profile directly
                        details = await s2_client.get_author_by_orcid(orcid_id)
                        if details:
                            match_source = "orcid"
                            confidence = 0.95  # High confidence
                
                # Step 2: Fall back to S2 name search
                if not details:
                    candidates = await s2_client.search_author(inv["full_name"])
                    
                    if candidates:
                        # Match by affiliation
                        match, conf = match_investigator(
                            inv["full_name"],
                            inv.get("affiliation"),
                            candidates
                        )
                        
                        if match:
                            # Get full details
                            details = await s2_client.get_author_details(match["authorId"])
                            if details:
                                match_source = "s2_affiliation"
                                confidence = conf
                
                if not details:
                    return False, ""
                
                # Extract data
                papers = details.get("papers") or []
                research_areas = extract_research_areas(papers)
                notable_papers = extract_notable_papers(papers)
                
                # Update database
                update_data = {
                    "semantic_scholar_id": details["authorId"],
                    "h_index": details.get("hIndex"),
                    "paper_count": details.get("paperCount"),
                    "citation_count": details.get("citationCount"),
                    "affiliations_s2": details.get("affiliations") or [],
                    "research_areas": research_areas,
                    "notable_papers": notable_papers,
                    "s2_match_confidence": confidence,
                    "s2_match_source": match_source,
                    "s2_enriched_at": datetime.now().isoformat()
                }
                
                # Add ORCID ID if found
                if orcid_id:
                    update_data["orcid_id"] = orcid_id
                
                supabase.table("investigators").update(update_data).eq("id", inv["id"]).execute()
                
                return True, match_source
                
            except Exception as e:
                print(f"  Error processing {inv['full_name']}: {e}")
                return False, ""
    
    # Process all investigators in batch concurrently
    tasks = [process_one(inv) for inv in investigators]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    for result in results:
        if isinstance(result, tuple) and result[0] is True:
            matched += 1
            if result[1] == "orcid":
                orcid_matched += 1
        else:
            failed += 1
    
    return matched, failed, orcid_matched


async def main(args):
    """Main enrichment loop."""
    
    # Check S2 API key
    if not S2_API_KEY:
        print("⚠️  WARNING: No SEMANTIC_SCHOLAR_API_KEY found!")
        print("   Rate limit: 100 requests per 5 minutes (~61 days for 738K investigators)")
        print("   Get a free API key: https://www.semanticscholar.org/product/api#api-key-form")
        if not args.force:
            print("\n   Use --force to proceed anyway, or add API key to .env")
            return
    else:
        print(f"✅ S2 API key found (rate: {S2_REQUESTS_PER_SECOND} req/sec)")
    
    # Check ORCID credentials
    use_orcid = not args.skip_orcid
    if use_orcid:
        if ORCID_CLIENT_ID and ORCID_CLIENT_SECRET:
            print(f"✅ ORCID credentials found (rate: {ORCID_REQUESTS_PER_SECOND} req/sec)")
        else:
            print("⚠️  ORCID credentials not found - using S2 only")
            print("   Add ORCID_CLIENT_ID and ORCID_CLIENT_SECRET to .env for better matching")
            use_orcid = False
    else:
        print("ℹ️  ORCID lookup disabled (--skip-orcid)")
    
    supabase = get_supabase_admin_client()
    checkpoint = Checkpoint()
    
    print(f"\n📊 Starting ORCID + Semantic Scholar enrichment")
    print(f"   Limit: {args.limit:,} investigators")
    print(f"   Batch size: {args.batch_size}")
    print(f"   Concurrency: {CONCURRENT_REQUESTS}")
    print(f"   ORCID enabled: {use_orcid}")
    
    if args.resume and checkpoint.data["last_processed_id"] > 0:
        print(f"   Resuming from ID: {checkpoint.data['last_processed_id']}")
        print(f"   Previous progress: {checkpoint.data['total_matched']:,} matched, {checkpoint.data['total_failed']:,} failed")
    
    # Build query for real PIs (not sponsors) - use smaller batches to avoid timeout
    print("\n📋 Fetching investigators from database...")
    
    investigators = []
    last_id = checkpoint.data["last_processed_id"] if args.resume else 0
    fetch_batch_size = min(1000, args.limit)  # Fetch in smaller chunks
    
    while len(investigators) < args.limit:
        try:
            query = supabase.table("investigators").select(
                "id, full_name, affiliation"
            ).is_("s2_enriched_at", "null")  # Not already enriched
            
            if last_id > 0:
                query = query.gt("id", last_id)
            
            remaining = args.limit - len(investigators)
            query = query.order("id").limit(min(fetch_batch_size, remaining))
            
            result = query.execute()
            
            if not result.data:
                break
            
            investigators.extend(result.data)
            last_id = result.data[-1]["id"]
            print(f"   Fetched {len(investigators):,} investigators so far...")
            
            # Small delay between fetches
            time.sleep(0.5)
            
        except Exception as e:
            print(f"   ⚠️ Fetch error: {e}, retrying in 5s...")
            time.sleep(5)
            continue
    
    if not investigators:
        print("\n✅ No investigators to process!")
        return
    
    # Filter out sponsors/organizations
    investigators = [
        inv for inv in investigators 
        if not is_likely_sponsor(inv["full_name"])
        and len(inv["full_name"]) > 5  # Skip very short names
    ]
    
    print(f"\n📋 Found {len(investigators):,} investigators to process")
    
    total_matched = 0
    total_failed = 0
    total_orcid_matched = 0
    semaphore = asyncio.Semaphore(CONCURRENT_REQUESTS)
    
    # Initialize clients
    async with SemanticScholarClient(S2_API_KEY) as s2_client:
        orcid_client = None
        if use_orcid:
            orcid_client = OrcidClient(ORCID_CLIENT_ID, ORCID_CLIENT_SECRET)
            await orcid_client.__aenter__()
        
        try:
            # Process in batches
            for i in range(0, len(investigators), args.batch_size):
                batch = investigators[i:i + args.batch_size]
                batch_num = i // args.batch_size + 1
                total_batches = (len(investigators) + args.batch_size - 1) // args.batch_size
                
                print(f"\n🔄 Batch {batch_num}/{total_batches} ({len(batch)} investigators)")
                
                matched, failed, orcid_matched = await enrich_batch(
                    s2_client, orcid_client, supabase, batch, semaphore, use_orcid
                )
                
                total_matched += matched
                total_failed += failed
                total_orcid_matched += orcid_matched
                
                # Update checkpoint
                last_id = batch[-1]["id"]
                checkpoint.update(last_id, matched, failed)
                
                # Progress
                match_rate = (matched / len(batch) * 100) if batch else 0
                orcid_rate = (orcid_matched / matched * 100) if matched else 0
                print(f"   ✓ Matched: {matched}/{len(batch)} ({match_rate:.1f}%)")
                if use_orcid:
                    print(f"   ✓ Via ORCID: {orcid_matched}/{matched} ({orcid_rate:.1f}%)")
                print(f"   Total: {total_matched:,} matched, {total_failed:,} failed")
                
                if args.dry_run:
                    print("   [DRY RUN - no database updates]")
                    break
        finally:
            if orcid_client:
                await orcid_client.__aexit__(None, None, None)
    
    # Final summary
    print(f"\n{'='*50}")
    print(f"✅ Enrichment complete!")
    print(f"   Total processed: {total_matched + total_failed:,}")
    total = total_matched + total_failed
    match_pct = (total_matched / total * 100) if total else 0
    print(f"   Matched: {total_matched:,} ({match_pct:.1f}%)")
    if use_orcid and total_matched > 0:
        orcid_pct = (total_orcid_matched / total_matched * 100)
        print(f"   Via ORCID: {total_orcid_matched:,} ({orcid_pct:.1f}%)")
        print(f"   Via S2 name: {total_matched - total_orcid_matched:,}")
    print(f"   Failed: {total_failed:,}")
    print(f"   Checkpoint saved to: {CHECKPOINT_FILE}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Enrich investigators with ORCID + Semantic Scholar data")
    parser.add_argument("--limit", type=int, default=10000, help="Max investigators to process")
    parser.add_argument("--batch-size", type=int, default=100, help="Batch size")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--dry-run", action="store_true", help="Search only, don't update DB")
    parser.add_argument("--force", action="store_true", help="Run without API key (slow)")
    parser.add_argument("--skip-orcid", action="store_true", help="Skip ORCID lookup, use S2 only")
    
    args = parser.parse_args()
    
    asyncio.run(main(args))
