"""Load parsed clinical trial data into Supabase."""

import asyncio
from typing import Any
from supabase import Client
from src.db.supabase_client import get_supabase_admin_client
from src.ingestion.parser import parse_study, normalize_facility_name


def fuzzy_match_score(s1: str | None, s2: str | None) -> float:
    """
    Simple fuzzy match score between two strings.
    Returns 0.0 to 1.0 based on substring containment.
    """
    if not s1 or not s2:
        return 0.0
    
    s1, s2 = s1.lower().strip(), s2.lower().strip()
    
    # Exact match
    if s1 == s2:
        return 1.0
    
    # One contains the other
    if s1 in s2 or s2 in s1:
        shorter, longer = (s1, s2) if len(s1) < len(s2) else (s2, s1)
        return len(shorter) / len(longer)
    
    return 0.0


class DataLoader:
    """Load clinical trial data into Supabase."""
    
    def __init__(self, client: Client | None = None):
        self.client = client or get_supabase_admin_client()
        
        # Caches to avoid duplicate lookups
        self._site_cache: dict[str, int] = {}  # (facility, city, country) -> id
        self._investigator_cache: dict[str, int] = {}  # (name, affiliation) -> id
        
    def _site_key(self, site: dict) -> str:
        """Create cache key for site."""
        return f"{site.get('facility_name')}|{site.get('city')}|{site.get('country')}"
    
    def _investigator_key(self, inv: dict) -> str:
        """Create cache key for investigator."""
        return f"{inv.get('full_name')}|{inv.get('affiliation')}"
    
    async def upsert_trial(self, trial: dict) -> int | None:
        """Insert or update a trial, return its ID."""
        try:
            # Remove raw_json for the upsert to avoid issues, we'll update it separately
            trial_data = {k: v for k, v in trial.items() if k != 'raw_json' and v is not None}
            
            result = self.client.table("trials").upsert(
                trial_data,
                on_conflict="nct_id"
            ).execute()
            
            if result.data:
                return result.data[0]["id"]
            return None
        except Exception as e:
            print(f"Error upserting trial {trial.get('nct_id')}: {e}")
            return None
    
    async def upsert_site(self, site: dict) -> int | None:
        """Insert or update a site, return its ID."""
        cache_key = self._site_key(site)
        
        if cache_key in self._site_cache:
            return self._site_cache[cache_key]
        
        try:
            site_data = {
                "facility_name": site.get("facility_name"),
                "facility_name_normalized": site.get("facility_name_normalized"),
                "city": site.get("city"),
                "state": site.get("state"),
                "country": site.get("country"),
                "zip": site.get("zip"),
            }
            # Remove None values
            site_data = {k: v for k, v in site_data.items() if v is not None}
            
            result = self.client.table("sites").upsert(
                site_data,
                on_conflict="facility_name,city,country"
            ).execute()
            
            if result.data:
                site_id = result.data[0]["id"]
                self._site_cache[cache_key] = site_id
                return site_id
            return None
        except Exception as e:
            print(f"Error upserting site {site.get('facility_name')}: {e}")
            return None
    
    async def upsert_investigator(self, investigator: dict) -> int | None:
        """Insert or update an investigator, return its ID."""
        cache_key = self._investigator_key(investigator)
        
        if cache_key in self._investigator_cache:
            return self._investigator_cache[cache_key]
        
        try:
            inv_data = {
                "full_name": investigator.get("full_name"),
                "name_normalized": investigator.get("name_normalized"),
                "role": investigator.get("role"),
                "affiliation": investigator.get("affiliation"),
                "affiliation_normalized": investigator.get("affiliation_normalized"),
            }
            inv_data = {k: v for k, v in inv_data.items() if v is not None}
            
            result = self.client.table("investigators").upsert(
                inv_data,
                on_conflict="full_name,affiliation"
            ).execute()
            
            if result.data:
                inv_id = result.data[0]["id"]
                self._investigator_cache[cache_key] = inv_id
                return inv_id
            return None
        except Exception as e:
            print(f"Error upserting investigator {investigator.get('full_name')}: {e}")
            return None
    
    async def link_trial_site(self, trial_id: int, site_id: int, status: str | None = None) -> bool:
        """Create trial-site relationship."""
        try:
            data = {
                "trial_id": trial_id,
                "site_id": site_id,
            }
            if status:
                data["recruitment_status"] = status
                
            self.client.table("trial_sites").upsert(
                data,
                on_conflict="trial_id,site_id"
            ).execute()
            return True
        except Exception as e:
            print(f"Error linking trial {trial_id} to site {site_id}: {e}")
            return False
    
    async def link_trial_investigator(self, trial_id: int, inv_id: int, role: str | None = None) -> bool:
        """Create trial-investigator relationship."""
        try:
            data = {
                "trial_id": trial_id,
                "investigator_id": inv_id,
            }
            if role:
                data["role"] = role
                
            self.client.table("trial_investigators").upsert(
                data,
                on_conflict="trial_id,investigator_id"
            ).execute()
            return True
        except Exception as e:
            print(f"Error linking trial {trial_id} to investigator {inv_id}: {e}")
            return False
    
    async def link_investigator_site(
        self,
        investigator_id: int,
        site_id: int,
        trial_id: int,
        link_type: str,
        link_confidence: float | None = None,
    ) -> bool:
        """
        Create investigator-site relationship.
        
        Args:
            investigator_id: ID of the investigator
            site_id: ID of the site
            trial_id: ID of the trial that established this link
            link_type: 'oversight' | 'affiliation_match' | 'site_contact'
            link_confidence: Confidence score (0-1) for heuristic matches
        """
        try:
            data = {
                "investigator_id": investigator_id,
                "site_id": site_id,
                "trial_id": trial_id,
                "link_type": link_type,
            }
            if link_confidence is not None:
                data["link_confidence"] = link_confidence
                
            self.client.table("investigator_sites").upsert(
                data,
                on_conflict="investigator_id,site_id,trial_id,link_type"
            ).execute()
            return True
        except Exception as e:
            print(f"Error linking investigator {investigator_id} to site {site_id}: {e}")
            return False
    
    async def load_study(self, study: dict) -> bool:
        """
        Load a single study (trial + sites + investigators) into the database.
        
        Creates three types of investigator-site links:
        1. oversight: overall officials linked to ALL trial sites
        2. affiliation_match: when official's affiliation matches a site name
        3. site_contact: explicit contacts listed under location.contacts
        
        Args:
            study: Raw study dict from CT.gov API
            
        Returns:
            True if successful
        """
        parsed = parse_study(study)
        
        # 1. Insert trial
        trial_id = await self.upsert_trial(parsed["trial"])
        if not trial_id:
            return False
        
        # 2. Insert sites and link to trial, track site_id by index
        site_ids_by_index: dict[int, int] = {}
        for site in parsed["sites"]:
            site_id = await self.upsert_site(site)
            if site_id:
                await self.link_trial_site(
                    trial_id, 
                    site_id, 
                    site.get("recruitment_status")
                )
                site_ids_by_index[site.get("_location_index")] = site_id
        
        all_site_ids = list(site_ids_by_index.values())
        
        # 3. Insert overall officials and create links
        for official in parsed["overall_officials"]:
            inv_id = await self.upsert_investigator(official)
            if not inv_id:
                continue
                
            # Link to trial
            await self.link_trial_investigator(trial_id, inv_id, official.get("role"))
            
            # Create investigator-site links
            affiliation_normalized = official.get("affiliation_normalized")
            
            for site in parsed["sites"]:
                site_id = site_ids_by_index.get(site.get("_location_index"))
                if not site_id:
                    continue
                
                # Link type 1: OVERSIGHT - overall official has oversight of all sites
                await self.link_investigator_site(
                    inv_id, site_id, trial_id,
                    link_type="oversight",
                    link_confidence=None,  # Not a heuristic, it's a fact
                )
                
                # Link type 2: AFFILIATION_MATCH - check if affiliation matches site
                if affiliation_normalized:
                    site_normalized = site.get("facility_name_normalized")
                    match_score = fuzzy_match_score(affiliation_normalized, site_normalized)
                    
                    if match_score >= 0.5:  # Threshold for affiliation match
                        await self.link_investigator_site(
                            inv_id, site_id, trial_id,
                            link_type="affiliation_match",
                            link_confidence=round(match_score, 2),
                        )
        
        # 4. Insert site contacts and create direct site links
        for contact in parsed["site_contacts"]:
            # Site contacts don't have affiliation, use site name as affiliation
            site_idx = contact.get("_site_index")
            site_id = site_ids_by_index.get(site_idx)
            
            if not site_id:
                continue
            
            # Find the site to get its name for the investigator record
            site_name = None
            for site in parsed["sites"]:
                if site.get("_location_index") == site_idx:
                    site_name = site.get("facility_name")
                    break
            
            # Create investigator with site as affiliation
            contact_inv = {
                "full_name": contact.get("full_name"),
                "name_normalized": contact.get("name_normalized"),
                "role": contact.get("role"),
                "affiliation": site_name,
                "affiliation_normalized": normalize_facility_name(site_name),
            }
            
            inv_id = await self.upsert_investigator(contact_inv)
            if not inv_id:
                continue
            
            # Link to trial
            await self.link_trial_investigator(trial_id, inv_id, contact.get("role"))
            
            # Link type 3: SITE_CONTACT - explicit site-level contact
            await self.link_investigator_site(
                inv_id, site_id, trial_id,
                link_type="site_contact",
                link_confidence=None,  # Explicit link, not heuristic
            )
        
        return True
    
    async def load_studies_batch(self, studies: list[dict]) -> tuple[int, int]:
        """
        Load a batch of studies.
        
        Returns:
            (success_count, failure_count)
        """
        success = 0
        failure = 0
        
        for study in studies:
            try:
                if await self.load_study(study):
                    success += 1
                else:
                    failure += 1
            except Exception as e:
                print(f"Error loading study: {e}")
                failure += 1
        
        return success, failure
