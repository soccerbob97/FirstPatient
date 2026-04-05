"""Trials API routes."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from api.schemas import (
    TrialListResponse,
    TrialDetail,
    TrialSummary,
)
from src.db.supabase_client import get_supabase_admin_client

router = APIRouter(prefix="/trials", tags=["trials"])


@router.get("", response_model=TrialListResponse)
async def list_trials(
    query: Optional[str] = Query(None, description="Search query"),
    phase: Optional[str] = Query(None, description="Filter by phase"),
    status: Optional[str] = Query(None, description="Filter by status"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List and search clinical trials.
    """
    try:
        client = get_supabase_admin_client()
        
        # Build query
        db_query = client.table("trials").select(
            "id, nct_id, brief_title, phase, overall_status, conditions, lead_sponsor_name",
            count="exact"
        )
        
        # Apply filters
        if query:
            db_query = db_query.or_(
                f"brief_title.ilike.%{query}%,nct_id.ilike.%{query}%"
            )
        
        if phase:
            db_query = db_query.eq("phase", phase)
        
        if status:
            db_query = db_query.eq("overall_status", status)
        
        # Pagination
        db_query = db_query.range(offset, offset + limit - 1)
        db_query = db_query.order("id", desc=True)
        
        result = db_query.execute()
        
        trials = [
            TrialSummary(
                id=t["id"],
                nct_id=t["nct_id"],
                brief_title=t.get("brief_title"),
                phase=t.get("phase"),
                overall_status=t.get("overall_status"),
                conditions=t.get("conditions"),
                lead_sponsor_name=t.get("lead_sponsor_name"),
            )
            for t in result.data
        ]
        
        return TrialListResponse(
            total=result.count or len(trials),
            limit=limit,
            offset=offset,
            trials=trials,
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{nct_id}", response_model=TrialDetail)
async def get_trial(nct_id: str):
    """
    Get detailed information about a specific trial.
    """
    try:
        client = get_supabase_admin_client()
        
        result = client.table("trials").select("*").eq("nct_id", nct_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail=f"Trial {nct_id} not found")
        
        t = result.data[0]
        
        return TrialDetail(
            id=t["id"],
            nct_id=t["nct_id"],
            brief_title=t.get("brief_title"),
            official_title=t.get("official_title"),
            brief_summary=t.get("brief_summary"),
            phase=t.get("phase"),
            study_type=t.get("study_type"),
            overall_status=t.get("overall_status"),
            conditions=t.get("conditions"),
            enrollment=t.get("enrollment"),
            start_date=str(t["start_date"]) if t.get("start_date") else None,
            completion_date=str(t["completion_date"]) if t.get("completion_date") else None,
            lead_sponsor_name=t.get("lead_sponsor_name"),
            lead_sponsor_class=t.get("lead_sponsor_class"),
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
