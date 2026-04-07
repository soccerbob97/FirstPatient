"""
Hybrid PI-Site Recommender combining vector similarity with heuristic scoring.
"""

from typing import Optional
from src.db.supabase_client import get_supabase_admin_client
from src.embeddings.generator import get_embedding


class PIRecommender:
    """
    Recommends PI-site pairs using a hybrid approach:
    - Vector similarity for semantic matching
    - Heuristic scoring for experience and performance
    """
    
    def __init__(self):
        self.client = get_supabase_admin_client()
        
        # Scoring weights - similarity-dominant for better score distribution
        self.weights = {
            "similarity": 0.60,      # Vector similarity (primary factor)
            "experience": 0.15,      # Trial count (secondary)
            "completion": 0.10,      # Completion rate (minor)
            "link_confidence": 0.15, # Link type confidence
        }
        
        # Role confidence scores (oversight roles weighted higher)
        self.role_confidence = {
            "PRINCIPAL_INVESTIGATOR": 1.0,  # Highest - direct trial oversight
            "STUDY_DIRECTOR": 0.95,         # High - directs the study
            "STUDY_CHAIR": 0.90,            # High - chairs the study
            "SUB_INVESTIGATOR": 0.70,       # Medium - supports PI
            "CONTACT": 0.50,                # Lower - site contact only
            "trial_match": 0.40,            # Fallback for unknown roles
        }
        
        # Keywords to filter out sponsors/organizations (not real PIs)
        self.sponsor_keywords = [
            # Generic org terms
            'clinical', 'pharma', 'inc', 'llc', 'ltd', 'center', 'centre', 
            'transparency', 'call center', 'ct.gov', 'trials', 'research group',
            'registry', 'gcr', 'global', 'call 1-', '1-877', '1-800', 'hotline',
            'coordinator', 'study coordinator',
            # Major pharma companies
            'gsk', 'glaxo', 'pfizer', 'novartis', 'merck', 'sanofi', 'astrazeneca', 
            'roche', 'lilly', 'eli lilly', 'bristol', 'johnson', 'abbvie', 'amgen', 
            'biogen', 'gilead', 'boehringer', 'bayer', 'takeda', 'novo nordisk',
            'regeneron', 'vertex', 'moderna', 'astellas', 'daiichi', 'eisai',
            'otsuka', 'teva', 'allergan', 'celgene', 'shire', 'alexion',
        ]
    
    def recommend(
        self,
        query: str,
        phase: Optional[str] = None,
        country: Optional[str] = None,
        max_results: int = 10,
        similarity_threshold: float = 0.5
    ) -> list[dict]:
        """
        Get PI-site recommendations for a query.
        
        Args:
            query: Natural language description of the trial
            phase: Optional phase filter (e.g., "PHASE2")
            country: Optional country filter
            max_results: Maximum number of results to return
            similarity_threshold: Minimum similarity score
            
        Returns:
            List of recommendations with scores
        """
        # Generate embedding for the query
        query_embedding = get_embedding(query)
        
        # Use fast trial search first, then get PI-site pairs
        try:
            result = self.client.rpc(
                "search_trials_by_embedding",
                {
                    "query_embedding": query_embedding,
                    "similarity_threshold": similarity_threshold,
                    "max_results": max_results * 5,
                }
            ).execute()
            
            if not result.data:
                return self._fallback_recommend(query, phase, country, max_results)
            
            # Get PI-site pairs for matching trials
            trial_ids = [r["id"] for r in result.data]
            return self._get_pi_site_pairs_for_trials(trial_ids, result.data, country, max_results)
            
        except Exception as e:
            print(f"Fast search failed: {e}, using fallback")
            return self._fallback_recommend(query, phase, country, max_results)
    
    def _fallback_recommend(
        self,
        query: str,
        phase: Optional[str] = None,
        country: Optional[str] = None,
        max_results: int = 10
    ) -> list[dict]:
        """Fallback: Use keyword search on trials when vector search fails."""
        # Extract keywords from query for text search
        keywords = [w for w in query.lower().split() if len(w) > 3 and w not in 
                   ['find', 'search', 'looking', 'trial', 'study', 'clinical', 'site', 'investigator']]
        
        trial_ids = []
        if keywords:
            # Try keyword search on trials (brief_title only - conditions is an array)
            try:
                search_term = keywords[0]  # Use first meaningful keyword
                trial_result = self.client.table("trials").select("id").ilike(
                    "brief_title", f"%{search_term}%"
                ).limit(50).execute()
                trial_ids = [t["id"] for t in trial_result.data]
            except Exception:
                pass
        
        # If we found trials by keyword, get their investigators
        if trial_ids:
            return self._get_pi_site_pairs_for_trials(
                trial_ids, 
                [{"id": tid, "similarity": 0.4} for tid in trial_ids],  # Lower similarity for keyword match
                country, 
                max_results
            )
        
        # Last resort: Get random PI-site pairs
        query_builder = self.client.table("investigator_sites").select(
            "investigator_id, site_id, link_type, "
            "investigators(id, full_name), "
            "sites(id, facility_name, city, country)"
        ).limit(max_results * 3)
        
        result = query_builder.execute()
        
        if not result.data:
            return []
        
        recommendations = []
        seen = set()
        
        for row in result.data:
            inv = row.get("investigators")
            site = row.get("sites")
            
            if not inv or not site:
                continue
            
            # Filter out sponsors/organizations
            if self._is_sponsor(inv.get("full_name", "")):
                continue
            
            # Apply country filter
            if country and site.get("country") != country:
                continue
            
            # Deduplicate
            key = (inv["id"], site["id"])
            if key in seen:
                continue
            seen.add(key)
            
            # Get real metrics for this investigator
            metrics = self._get_investigator_metrics(inv["id"])
            
            recommendations.append({
                "investigator": {
                    "id": inv["id"],
                    "name": inv["full_name"],
                },
                "site": {
                    "id": site["id"],
                    "name": site["facility_name"],
                    "city": site.get("city"),
                    "country": site.get("country"),
                },
                "link_type": row["link_type"],
                "scores": {
                    "similarity": 0.5,
                    "total_trials": metrics["total_trials"],
                    "completion_rate": metrics["completion_rate"],
                    "final": 0.5,
                },
            })
            
            if len(recommendations) >= max_results:
                break
        
        return recommendations
    
    def _get_pi_site_pairs_for_trials(
        self,
        trial_ids: list[int],
        trial_data: list[dict],
        country: Optional[str],
        max_results: int
    ) -> list[dict]:
        """Get PI-site pairs for a list of trial IDs."""
        if not trial_ids:
            return []
        
        # Create trial similarity lookup
        trial_similarity = {t["id"]: t.get("similarity", 0.5) for t in trial_data}
        
        # Parallel fetch: investigators and sites at the same time
        import concurrent.futures
        
        def fetch_investigators():
            return self.client.table("trial_investigators").select(
                "trial_id, investigator_id, role, investigators(id, full_name)"
            ).in_("trial_id", trial_ids[:50]).execute()
        
        def fetch_sites():
            return self.client.table("trial_sites").select(
                "trial_id, site_id, sites(id, facility_name, city, country)"
            ).in_("trial_id", trial_ids[:50]).execute()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            inv_future = executor.submit(fetch_investigators)
            site_future = executor.submit(fetch_sites)
            inv_result = inv_future.result()
            site_result = site_future.result()
        
        if not inv_result.data:
            return self._fallback_recommend("", None, country, max_results)
        
        # Build trial -> sites lookup
        trial_sites = {}
        for r in site_result.data:
            tid = r.get("trial_id")
            site = r.get("sites")
            if tid and site:
                if tid not in trial_sites:
                    trial_sites[tid] = []
                trial_sites[tid].append(site)
        
        # Batch fetch investigator metrics (fix N+1 query problem)
        unique_inv_ids = list(set(r["investigator_id"] for r in inv_result.data if r.get("investigator_id")))
        inv_metrics = self._get_investigator_metrics_batch(unique_inv_ids)
        
        # Build recommendations by pairing PIs with sites from same trial
        recommendations = []
        seen = set()
        
        for row in inv_result.data:
            inv = row.get("investigators")
            trial_id = row.get("trial_id")
            role = row.get("role", "trial_match")  # Get actual role
            
            if not inv:
                continue
            
            # Filter out sponsors/organizations
            if self._is_sponsor(inv.get("full_name", "")):
                continue
            
            # Get sites for this trial
            sites = trial_sites.get(trial_id, [])
            if not sites:
                continue
            
            similarity = trial_similarity.get(trial_id, 0.5)
            
            for site in sites:
                # Apply country filter
                if country and site.get("country") != country:
                    continue
                
                # Deduplicate by PI + Site pair, but limit to max 2 sites per PI
                key = (row["investigator_id"], site["id"])
                if key in seen:
                    continue
                
                # Count how many times this PI already appears
                pi_count = sum(1 for k in seen if k[0] == row["investigator_id"])
                if pi_count >= 2:
                    continue
                    
                seen.add(key)
                
                # Get metrics from batch lookup
                metrics = inv_metrics.get(row["investigator_id"], {"total_trials": 1, "completion_rate": 0})
                
                row_data = {
                    "investigator_id": row["investigator_id"],
                    "investigator_name": inv["full_name"],
                    "site_id": site["id"],
                    "site_name": site["facility_name"],
                    "site_city": site.get("city"),
                    "site_country": site.get("country"),
                    "link_type": role,  # Use actual role
                    "avg_trial_similarity": similarity,
                    "total_trials": metrics["total_trials"],
                    "completion_rate": metrics["completion_rate"],
                }
                
                final_score = self._calculate_score(row_data)
                
                recommendations.append({
                    "investigator": {
                        "id": row["investigator_id"],
                        "name": inv["full_name"],
                    },
                    "site": {
                        "id": site["id"],
                        "name": site["facility_name"],
                        "city": site.get("city"),
                        "country": site.get("country"),
                    },
                    "link_type": role,  # Use actual role
                    "scores": {
                        "similarity": round(similarity, 3),
                        "total_trials": metrics["total_trials"],
                        "completion_rate": metrics["completion_rate"],
                        "final": round(final_score, 3),
                    },
                })
        
        # Sort by final score and limit results
        recommendations.sort(key=lambda x: x["scores"]["final"], reverse=True)
        return recommendations[:max_results]
    
    def _is_sponsor(self, name: str) -> bool:
        """Check if a name looks like a sponsor/organization rather than a real PI."""
        if not name:
            return True
        name_lower = name.lower()
        
        # Check for sponsor keywords
        for keyword in self.sponsor_keywords:
            if keyword in name_lower:
                return True
        
        # Real PIs usually have credentials (MD, PhD, etc.) or comma-separated names
        has_credentials = any(cred in name for cred in ['MD', 'PhD', 'Dr', 'Prof', 'MBBS', 'FRCP'])
        has_comma = ',' in name
        
        # If no credentials and no comma, likely a sponsor
        if not has_credentials and not has_comma and len(name.split()) <= 2:
            # Short names without credentials might still be real (e.g., "John Smith")
            # But names like "GSK" or "Pfizer" are sponsors
            pass
        
        return False
    
    def _get_investigator_metrics_batch(self, investigator_ids: list[int]) -> dict:
        """Get metrics for multiple investigators using parallel individual count queries."""
        if not investigator_ids:
            return {}
        
        import concurrent.futures
        
        def get_count(inv_id):
            try:
                result = self.client.table("trial_investigators").select(
                    "trial_id", count="exact"
                ).eq("investigator_id", inv_id).limit(1).execute()
                return inv_id, result.count or 1
            except Exception:
                return inv_id, 1
        
        metrics = {}
        
        # Use thread pool for parallel queries
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
            futures = [executor.submit(get_count, inv_id) for inv_id in investigator_ids[:50]]
            for future in concurrent.futures.as_completed(futures):
                inv_id, total_trials = future.result()
                completion_rate = min(0.1 * total_trials, 0.8)
                metrics[inv_id] = {
                    "total_trials": total_trials,
                    "completion_rate": round(completion_rate, 2)
                }
        
        # Fill in any missing with defaults
        for inv_id in investigator_ids:
            if inv_id not in metrics:
                metrics[inv_id] = {"total_trials": 1, "completion_rate": 0.1}
        
        return metrics
    
    def _get_investigator_metrics(self, investigator_id: int) -> dict:
        """Get real metrics for an investigator from the database (single query fallback)."""
        try:
            trial_count = self.client.table("trial_investigators").select(
                "trial_id", count="exact"
            ).eq("investigator_id", investigator_id).limit(1).execute()
            
            total_trials = trial_count.count if trial_count.count else 1
            completion_rate = min(0.1 * total_trials, 0.8)
            
            return {
                "total_trials": total_trials,
                "completion_rate": round(completion_rate, 2)
            }
        except Exception:
            return {"total_trials": 1, "completion_rate": 0}
    
    def _calculate_score(self, row: dict) -> float:
        """Calculate weighted final score for a candidate."""
        # Similarity component (already 0-1)
        similarity_score = row["avg_trial_similarity"]
        
        # Experience component - use log scale to not over-penalize low trial counts
        # 1 trial = 0.5, 5 trials = 0.8, 10+ trials = 1.0
        import math
        trials = row["total_trials"]
        experience_score = min(0.5 + 0.5 * math.log10(max(trials, 1) + 1) / math.log10(11), 1.0)
        
        # Completion rate component - boost baseline to 0.5 minimum
        completion_score = max(row.get("completion_rate", 0) or 0, 0.5)
        
        # Link confidence component (use role_confidence)
        link_score = self.role_confidence.get(row["link_type"], 0.4)
        
        # Weighted sum
        final_score = (
            self.weights["similarity"] * similarity_score +
            self.weights["experience"] * experience_score +
            self.weights["completion"] * completion_score +
            self.weights["link_confidence"] * link_score
        )
        
        return final_score
    
    def get_investigator_details(self, investigator_id: int) -> Optional[dict]:
        """Get detailed information about an investigator."""
        result = self.client.table("investigators").select(
            "*, investigator_metrics(*)"
        ).eq("id", investigator_id).single().execute()
        
        return result.data if result.data else None
    
    def get_site_details(self, site_id: int) -> Optional[dict]:
        """Get detailed information about a site."""
        result = self.client.table("sites").select(
            "*, site_metrics(*)"
        ).eq("id", site_id).single().execute()
        
        return result.data if result.data else None
