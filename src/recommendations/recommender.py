"""Recommendation engine for PI + Site matching using hybrid search."""

from typing import List, Optional
from dataclasses import dataclass

from src.db.supabase_client import get_supabase_admin_client
from src.embeddings.generator import get_embedding


@dataclass
class Recommendation:
    """A PI + Site recommendation."""
    investigator_id: int
    investigator_name: str
    site_id: int
    site_name: str
    site_city: str
    site_country: str
    link_type: str
    similarity_score: float
    total_trials: int
    completion_rate: float
    final_score: float
    
    def to_dict(self) -> dict:
        return {
            "investigator": {
                "id": self.investigator_id,
                "name": self.investigator_name,
            },
            "site": {
                "id": self.site_id,
                "name": self.site_name,
                "city": self.site_city,
                "country": self.site_country,
            },
            "link_type": self.link_type,
            "scores": {
                "similarity": round(self.similarity_score, 3),
                "total_trials": self.total_trials,
                "completion_rate": round(self.completion_rate, 3) if self.completion_rate else 0,
                "final": round(self.final_score, 3),
            }
        }


class PIRecommender:
    """
    Hybrid recommendation engine combining:
    1. Vector similarity search (semantic relevance)
    2. Heuristic scoring (experience, completion rate, geography)
    """
    
    def __init__(self):
        self.client = get_supabase_admin_client()
    
    def recommend(
        self,
        query: str,
        phase: Optional[str] = None,
        country: Optional[str] = None,
        similarity_threshold: float = 0.5,
        max_results: int = 20,
    ) -> List[Recommendation]:
        """
        Get PI + Site recommendations for a clinical trial query.
        
        Args:
            query: Natural language description of the trial
                   e.g., "Phase 2 oncology trial for breast cancer"
            phase: Filter by phase (e.g., "PHASE2")
            country: Filter by country (e.g., "United States")
            similarity_threshold: Minimum similarity score (0-1)
            max_results: Maximum number of recommendations
            
        Returns:
            List of Recommendation objects, sorted by final_score
        """
        # Step 1: Embed the query
        query_embedding = get_embedding(query)
        
        if not query_embedding:
            return []
        
        # Step 2: Call the database function
        result = self.client.rpc(
            "recommend_pi_site_pairs",
            {
                "query_embedding": query_embedding,
                "target_phase": phase,
                "target_country": country,
                "similarity_threshold": similarity_threshold,
                "max_results": max_results,
            }
        ).execute()
        
        # Step 3: Convert to Recommendation objects
        recommendations = []
        for row in result.data:
            rec = Recommendation(
                investigator_id=row["investigator_id"],
                investigator_name=row["investigator_name"],
                site_id=row["site_id"],
                site_name=row["site_name"],
                site_city=row["site_city"],
                site_country=row["site_country"],
                link_type=row["link_type"],
                similarity_score=row["avg_trial_similarity"] or 0,
                total_trials=row["total_trials"] or 0,
                completion_rate=row["completion_rate"] or 0,
                final_score=row["final_score"] or 0,
            )
            recommendations.append(rec)
        
        return recommendations
    
    def recommend_by_trial(
        self,
        nct_id: str,
        country: Optional[str] = None,
        max_results: int = 20,
    ) -> List[Recommendation]:
        """
        Get PI + Site recommendations based on an existing trial.
        
        Useful for: "Find PIs who could run a trial similar to NCT12345678"
        
        Args:
            nct_id: NCT ID of the reference trial
            country: Filter by country
            max_results: Maximum number of recommendations
            
        Returns:
            List of Recommendation objects
        """
        # Get the trial's embedding
        result = self.client.table("trials").select(
            "embedding, phase"
        ).eq("nct_id", nct_id).execute()
        
        if not result.data or not result.data[0].get("embedding"):
            return []
        
        trial = result.data[0]
        
        # Use the trial's embedding directly
        result = self.client.rpc(
            "recommend_pi_site_pairs",
            {
                "query_embedding": trial["embedding"],
                "target_phase": trial.get("phase"),
                "target_country": country,
                "similarity_threshold": 0.7,  # Higher threshold for similar trials
                "max_results": max_results,
            }
        ).execute()
        
        recommendations = []
        for row in result.data:
            rec = Recommendation(
                investigator_id=row["investigator_id"],
                investigator_name=row["investigator_name"],
                site_id=row["site_id"],
                site_name=row["site_name"],
                site_city=row["site_city"],
                site_country=row["site_country"],
                link_type=row["link_type"],
                similarity_score=row["avg_trial_similarity"] or 0,
                total_trials=row["total_trials"] or 0,
                completion_rate=row["completion_rate"] or 0,
                final_score=row["final_score"] or 0,
            )
            recommendations.append(rec)
        
        return recommendations
    
    def search_investigators(
        self,
        query: str,
        similarity_threshold: float = 0.6,
        max_results: int = 20,
    ) -> List[dict]:
        """
        Search for investigators by expertise using semantic search.
        
        Args:
            query: Natural language expertise query
                   e.g., "CAR-T cell therapy expert"
            similarity_threshold: Minimum similarity score
            max_results: Maximum results
            
        Returns:
            List of investigator dicts with similarity scores
        """
        query_embedding = get_embedding(query)
        
        if not query_embedding:
            return []
        
        result = self.client.rpc(
            "search_investigators_by_embedding",
            {
                "query_embedding": query_embedding,
                "similarity_threshold": similarity_threshold,
                "max_results": max_results,
            }
        ).execute()
        
        return result.data
    
    def search_trials(
        self,
        query: str,
        similarity_threshold: float = 0.6,
        max_results: int = 50,
    ) -> List[dict]:
        """
        Search for trials using semantic search.
        
        Args:
            query: Natural language trial description
            similarity_threshold: Minimum similarity score
            max_results: Maximum results
            
        Returns:
            List of trial dicts with similarity scores
        """
        query_embedding = get_embedding(query)
        
        if not query_embedding:
            return []
        
        result = self.client.rpc(
            "search_trials_by_embedding",
            {
                "query_embedding": query_embedding,
                "similarity_threshold": similarity_threshold,
                "max_results": max_results,
            }
        ).execute()
        
        return result.data


# Convenience function
def get_recommendations(
    query: str,
    phase: Optional[str] = None,
    country: Optional[str] = None,
    max_results: int = 20,
) -> List[dict]:
    """
    Get PI + Site recommendations as dictionaries.
    
    Args:
        query: Natural language trial description
        phase: Optional phase filter
        country: Optional country filter
        max_results: Maximum recommendations
        
    Returns:
        List of recommendation dictionaries
    """
    recommender = PIRecommender()
    recommendations = recommender.recommend(
        query=query,
        phase=phase,
        country=country,
        max_results=max_results,
    )
    return [r.to_dict() for r in recommendations]
