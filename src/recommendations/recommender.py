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
        
        # Scoring weights
        self.weights = {
            "similarity": 0.40,      # Vector similarity
            "experience": 0.25,      # Trial count
            "completion": 0.20,      # Completion rate
            "link_confidence": 0.15, # Link type confidence
        }
        
        # Link type confidence scores
        self.link_confidence = {
            "oversight": 0.9,        # Direct oversight relationship
            "site_contact": 0.7,     # Listed as site contact
            "affiliation_match": 0.5 # Matched by affiliation
        }
    
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
        
        # Call the database function for hybrid search
        result = self.client.rpc(
            "recommend_pi_site_pairs",
            {
                "query_embedding": query_embedding,
                "similarity_threshold": similarity_threshold,
                "max_results": max_results * 3,  # Get more candidates for filtering
                "target_phase": phase,
                "target_country": country,
            }
        ).execute()
        
        if not result.data:
            return []
        
        # Process and re-rank results
        recommendations = []
        for row in result.data:
            # Calculate final score using our weights
            final_score = self._calculate_score(row)
            
            recommendations.append({
                "investigator": {
                    "id": row["investigator_id"],
                    "name": row["investigator_name"],
                },
                "site": {
                    "id": row["site_id"],
                    "name": row["site_name"],
                    "city": row["site_city"],
                    "country": row["site_country"],
                },
                "link_type": row["link_type"],
                "scores": {
                    "similarity": round(row["avg_trial_similarity"], 3),
                    "total_trials": row["total_trials"],
                    "completion_rate": round(row.get("completion_rate", 0) or 0, 3),
                    "final": round(final_score, 3),
                },
            })
        
        # Sort by final score and limit results
        recommendations.sort(key=lambda x: x["scores"]["final"], reverse=True)
        return recommendations[:max_results]
    
    def _calculate_score(self, row: dict) -> float:
        """Calculate weighted final score for a candidate."""
        # Similarity component (already 0-1)
        similarity_score = row["avg_trial_similarity"]
        
        # Experience component (normalize by max expected trials)
        max_expected_trials = 20
        experience_score = min(row["total_trials"] / max_expected_trials, 1.0)
        
        # Completion rate component (already 0-1)
        completion_score = row.get("completion_rate", 0) or 0
        
        # Link confidence component
        link_score = self.link_confidence.get(row["link_type"], 0.5)
        
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
