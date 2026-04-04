"""ClinicalTrials.gov API client for fetching study data."""

import asyncio
import httpx
from typing import AsyncIterator
from dataclasses import dataclass
from src.config import get_config


@dataclass
class StudyPage:
    """A page of studies from the API."""
    studies: list[dict]
    next_page_token: str | None
    total_count: int


class ClinicalTrialsClient:
    """Client for ClinicalTrials.gov v2 API."""
    
    # Fields we need from the API (reduces payload size significantly)
    FIELDS = [
        # Identification
        "NCTId",
        "OrgStudyId",
        "BriefTitle",
        "OfficialTitle",
        
        # Description
        "BriefSummary",
        
        # Conditions
        "Condition",
        
        # Design
        "Phase",
        "StudyType",
        
        # Status
        "OverallStatus",
        "StartDate",
        "CompletionDate",
        "PrimaryCompletionDate",
        
        # Enrollment
        "EnrollmentCount",
        "EnrollmentType",
        
        # Sponsor
        "LeadSponsorName",
        "LeadSponsorClass",
        
        # Dates
        "LastUpdatePostDate",
        
        # Locations (sites)
        "LocationFacility",
        "LocationCity",
        "LocationState",
        "LocationZip",
        "LocationCountry",
        "LocationStatus",
        
        # Officials (investigators)
        "OverallOfficialName",
        "OverallOfficialAffiliation",
        "OverallOfficialRole",
    ]
    
    def __init__(self):
        self.config = get_config().clinical_trials
        self.base_url = self.config.base_url
        
    async def fetch_page(
        self,
        client: httpx.AsyncClient,
        page_token: str | None = None,
        query: str | None = None,
    ) -> StudyPage:
        """Fetch a single page of studies."""
        params = {
            "format": "json",
            "pageSize": self.config.page_size,
            "fields": "|".join(self.FIELDS),
        }
        
        if page_token:
            params["pageToken"] = page_token
        if query:
            params["query.term"] = query
            
        url = f"{self.base_url}/studies"
        
        for attempt in range(self.config.max_retries):
            try:
                response = await client.get(url, params=params, timeout=60.0)
                response.raise_for_status()
                data = response.json()
                
                return StudyPage(
                    studies=data.get("studies", []),
                    next_page_token=data.get("nextPageToken"),
                    total_count=data.get("totalCount", 0),
                )
            except (httpx.HTTPError, httpx.TimeoutException) as e:
                if attempt < self.config.max_retries - 1:
                    print(f"Retry {attempt + 1}/{self.config.max_retries} after error: {e}")
                    await asyncio.sleep(self.config.retry_delay)
                else:
                    raise
                    
    async def fetch_all_studies(
        self,
        query: str | None = None,
        progress_callback=None,
    ) -> AsyncIterator[list[dict]]:
        """
        Fetch all studies, yielding pages as they come.
        
        Args:
            query: Optional search query to filter studies
            progress_callback: Optional callback(fetched_count, total_count)
            
        Yields:
            Lists of study dictionaries
        """
        async with httpx.AsyncClient() as client:
            page_token = None
            fetched = 0
            
            # First request to get total count
            page = await self.fetch_page(client, page_token, query)
            total = page.total_count
            
            print(f"Total studies to fetch: {total:,}")
            
            while True:
                yield page.studies
                fetched += len(page.studies)
                
                if progress_callback:
                    progress_callback(fetched, total)
                else:
                    print(f"Fetched {fetched:,} / {total:,} ({100*fetched/total:.1f}%)")
                
                if not page.next_page_token:
                    break
                    
                # Rate limiting
                await asyncio.sleep(self.config.rate_limit_delay)
                
                page = await self.fetch_page(client, page.next_page_token, query)
                
    async def fetch_study_by_nct_id(self, nct_id: str) -> dict | None:
        """Fetch a single study by NCT ID."""
        async with httpx.AsyncClient() as client:
            url = f"{self.base_url}/studies/{nct_id}"
            params = {"format": "json"}
            
            try:
                response = await client.get(url, params=params, timeout=30.0)
                response.raise_for_status()
                return response.json()
            except httpx.HTTPStatusError as e:
                if e.response.status_code == 404:
                    return None
                raise
