"""Recommendations API routes."""

from fastapi import APIRouter, HTTPException

from api.schemas import (
    RecommendationRequest,
    RecommendationResponse,
    Recommendation,
    InvestigatorInfo,
    SiteInfo,
    ScoreBreakdown,
)
from src.recommendations.recommender import PIRecommender

router = APIRouter(prefix="/recommendations", tags=["recommendations"])


@router.post("", response_model=RecommendationResponse)
async def get_recommendations(request: RecommendationRequest):
    """
    Get PI + Site recommendations for a clinical trial query.
    
    Uses hybrid search combining:
    - Vector similarity (semantic relevance)
    - Heuristic scoring (experience, completion rate, link confidence)
    """
    try:
        recommender = PIRecommender()
        results = recommender.recommend(
            query=request.query,
            phase=request.phase,
            country=request.country,
            similarity_threshold=request.similarity_threshold,
            max_results=request.max_results,
        )
        
        recommendations = []
        for r in results:
            rec = Recommendation(
                investigator=InvestigatorInfo(
                    id=r["investigator"]["id"],
                    name=r["investigator"]["name"],
                ),
                site=SiteInfo(
                    id=r["site"]["id"],
                    name=r["site"]["name"],
                    city=r["site"]["city"],
                    country=r["site"]["country"],
                ),
                link_type=r["link_type"],
                scores=ScoreBreakdown(
                    similarity=r["scores"]["similarity"],
                    total_trials=r["scores"]["total_trials"],
                    completion_rate=r["scores"]["completion_rate"],
                    final=r["scores"]["final"],
                ),
            )
            recommendations.append(rec)
        
        return RecommendationResponse(
            query=request.query,
            total_results=len(recommendations),
            recommendations=recommendations,
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
