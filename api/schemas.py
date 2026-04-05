"""Pydantic schemas for API request/response models."""

from typing import List, Optional
from pydantic import BaseModel, Field


# ============================================
# REQUEST SCHEMAS
# ============================================

class RecommendationRequest(BaseModel):
    """Request body for getting PI+Site recommendations."""
    query: str = Field(..., description="Natural language description of the trial", min_length=3)
    phase: Optional[str] = Field(None, description="Filter by phase (e.g., 'PHASE2')")
    country: Optional[str] = Field(None, description="Filter by country (e.g., 'United States')")
    max_results: int = Field(10, ge=1, le=50, description="Maximum number of recommendations")
    similarity_threshold: float = Field(0.5, ge=0.0, le=1.0, description="Minimum similarity score")

    class Config:
        json_schema_extra = {
            "example": {
                "query": "Phase 2 oncology trial for breast cancer",
                "phase": "PHASE2",
                "country": "United States",
                "max_results": 10
            }
        }


class TrialSearchRequest(BaseModel):
    """Request body for searching trials."""
    query: Optional[str] = Field(None, description="Search query")
    phase: Optional[str] = Field(None, description="Filter by phase")
    status: Optional[str] = Field(None, description="Filter by status")
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


class InvestigatorSearchRequest(BaseModel):
    """Request body for searching investigators."""
    query: Optional[str] = Field(None, description="Search query (name or expertise)")
    limit: int = Field(20, ge=1, le=100)
    offset: int = Field(0, ge=0)


# ============================================
# RESPONSE SCHEMAS
# ============================================

class InvestigatorInfo(BaseModel):
    """Investigator information in a recommendation."""
    id: int
    name: str


class SiteInfo(BaseModel):
    """Site information in a recommendation."""
    id: int
    name: str
    city: Optional[str]
    country: Optional[str]


class ScoreBreakdown(BaseModel):
    """Score breakdown for a recommendation."""
    similarity: float
    total_trials: int
    completion_rate: float
    final: float


class Recommendation(BaseModel):
    """A single PI+Site recommendation."""
    investigator: InvestigatorInfo
    site: SiteInfo
    link_type: str
    scores: ScoreBreakdown


class RecommendationResponse(BaseModel):
    """Response for recommendations endpoint."""
    query: str
    total_results: int
    recommendations: List[Recommendation]


class TrialSummary(BaseModel):
    """Summary of a trial for list views."""
    id: int
    nct_id: str
    brief_title: Optional[str]
    phase: Optional[str]
    overall_status: Optional[str]
    conditions: Optional[List[str]]
    lead_sponsor_name: Optional[str]


class TrialDetail(BaseModel):
    """Detailed trial information."""
    id: int
    nct_id: str
    brief_title: Optional[str]
    official_title: Optional[str]
    brief_summary: Optional[str]
    phase: Optional[str]
    study_type: Optional[str]
    overall_status: Optional[str]
    conditions: Optional[List[str]]
    enrollment: Optional[int]
    start_date: Optional[str]
    completion_date: Optional[str]
    lead_sponsor_name: Optional[str]
    lead_sponsor_class: Optional[str]


class TrialListResponse(BaseModel):
    """Response for trial list endpoint."""
    total: int
    limit: int
    offset: int
    trials: List[TrialSummary]


class InvestigatorSummary(BaseModel):
    """Summary of an investigator."""
    id: int
    full_name: str
    affiliation: Optional[str]
    trial_count: Optional[int] = 0


class InvestigatorListResponse(BaseModel):
    """Response for investigator list endpoint."""
    total: int
    limit: int
    offset: int
    investigators: List[InvestigatorSummary]


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
