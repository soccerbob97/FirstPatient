"""Investigators API routes."""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional

from api.schemas import (
    InvestigatorListResponse,
    InvestigatorSummary,
)
from src.db.supabase_client import get_supabase_admin_client

router = APIRouter(prefix="/investigators", tags=["investigators"])


@router.get("", response_model=InvestigatorListResponse)
async def list_investigators(
    query: Optional[str] = Query(None, description="Search by name or affiliation"),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """
    List and search investigators.
    """
    try:
        client = get_supabase_admin_client()
        
        # Build query
        db_query = client.table("investigators").select(
            "id, full_name, affiliation",
            count="exact"
        )
        
        # Apply search filter
        if query:
            db_query = db_query.or_(
                f"full_name.ilike.%{query}%,affiliation.ilike.%{query}%"
            )
        
        # Pagination
        db_query = db_query.range(offset, offset + limit - 1)
        db_query = db_query.order("full_name")
        
        result = db_query.execute()
        
        # Get trial counts for each investigator
        investigators = []
        for inv in result.data:
            # Get trial count
            count_result = client.table("trial_investigators").select(
                "id", count="exact"
            ).eq("investigator_id", inv["id"]).execute()
            
            investigators.append(
                InvestigatorSummary(
                    id=inv["id"],
                    full_name=inv["full_name"],
                    affiliation=inv.get("affiliation"),
                    trial_count=count_result.count or 0,
                )
            )
        
        return InvestigatorListResponse(
            total=result.count or len(investigators),
            limit=limit,
            offset=offset,
            investigators=investigators,
        )
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{investigator_id}")
async def get_investigator(investigator_id: int):
    """
    Get detailed information about a specific investigator.
    """
    try:
        client = get_supabase_admin_client()
        
        # Get investigator
        result = client.table("investigators").select("*").eq("id", investigator_id).execute()
        
        if not result.data:
            raise HTTPException(status_code=404, detail=f"Investigator {investigator_id} not found")
        
        inv = result.data[0]
        
        # Get their trials
        trials_result = client.table("trial_investigators").select(
            "trials(nct_id, brief_title, phase, overall_status)"
        ).eq("investigator_id", investigator_id).execute()
        
        trials = [t["trials"] for t in trials_result.data if t.get("trials")]
        
        # Get their sites
        sites_result = client.table("investigator_sites").select(
            "link_type, sites(facility_name, city, country)"
        ).eq("investigator_id", investigator_id).execute()
        
        sites = [
            {
                "link_type": s["link_type"],
                **s["sites"]
            }
            for s in sites_result.data if s.get("sites")
        ]
        
        return {
            "id": inv["id"],
            "full_name": inv["full_name"],
            "affiliation": inv.get("affiliation"),
            "expertise_profile": inv.get("expertise_profile"),
            "trial_count": len(trials),
            "trials": trials[:10],  # Limit to 10 most recent
            "sites": sites,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
