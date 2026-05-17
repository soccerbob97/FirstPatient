"""
Protocol Intelligence API Routes
Endpoints for protocol parsing, scoring, and recommendations
"""

import os
import tempfile
from typing import Optional
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import List, Dict, Any

router = APIRouter(prefix="/protocol", tags=["Protocol Intelligence"])


class ProtocolAnalysisRequest(BaseModel):
    """Request body for protocol analysis from text"""
    protocol_text: str = Field(..., description="Raw protocol text to analyze")
    include_recommendations: bool = Field(True, description="Include PI/site recommendations")
    recommendation_limit: int = Field(10, description="Max number of PI recommendations")


class ProtocolAnalysisResponse(BaseModel):
    """Response from protocol analysis"""
    success: bool
    protocol_id: str
    metadata: Dict[str, Any]
    eligibility: Dict[str, Any]
    study_design: Dict[str, Any]
    visit_schedule: Dict[str, Any]
    assessments: Dict[str, Any]
    safety_monitoring: Dict[str, Any]
    endpoints: Dict[str, Any]
    sample_size: Dict[str, Any]
    scores: Dict[str, Any]
    recommendations: Optional[Dict[str, Any]] = None
    parsing_confidence: float
    parsing_notes: List[str]


class QuickScoreRequest(BaseModel):
    """Request for quick scoring without full parsing"""
    phase: str = Field(..., description="Study phase (e.g., 'Phase 1', 'Phase 2')")
    therapeutic_area: str = Field(..., description="Therapeutic area (e.g., 'Oncology')")
    indication: str = Field("", description="Specific indication")
    
    # Eligibility
    inclusion_criteria_count: int = Field(10, ge=0)
    exclusion_criteria_count: int = Field(10, ge=0)
    requires_biomarker: bool = Field(False)
    requires_prior_therapy: bool = Field(False)
    
    # Study design
    number_of_arms: int = Field(1, ge=1)
    blinding: str = Field("open-label", description="open-label, single-blind, double-blind")
    treatment_duration_weeks: int = Field(12, ge=1)
    adaptive_design: bool = Field(False)
    dose_escalation: bool = Field(False)
    
    # Visits and assessments
    total_visits: int = Field(10, ge=1)
    imaging_modalities: int = Field(0, ge=0)
    pk_sampling: bool = Field(False)
    pk_timepoints: int = Field(0, ge=0)
    biopsies_required: bool = Field(False)
    
    # Safety
    dsmb_required: bool = Field(False)
    cardiac_monitoring: bool = Field(False)
    
    # Sample size
    target_enrollment: int = Field(100, ge=1)


class QuickScoreResponse(BaseModel):
    """Response from quick scoring"""
    success: bool
    overall_complexity: float
    enrollment_difficulty: Dict[str, Any]
    site_burden: Dict[str, Any]
    operational_complexity: Dict[str, Any]
    amendment_risk: Dict[str, Any]
    monitoring_complexity: Dict[str, Any]
    patient_burden: Dict[str, Any]
    estimated_enrollment_rate: float
    estimated_screen_fail_rate: float
    recommended_site_profile: Dict[str, Any]
    recommended_pi_profile: Dict[str, Any]


def get_parser():
    """Get protocol parser instance"""
    from src.protocol_intelligence.parser import ProtocolParser
    return ProtocolParser()


def get_scorer():
    """Get protocol scorer instance"""
    from src.protocol_intelligence.scoring import ProtocolScorer
    return ProtocolScorer()


def get_recommender():
    """Get protocol recommender instance"""
    from src.protocol_intelligence.recommender import ProtocolRecommender
    return ProtocolRecommender()


@router.post("/analyze", response_model=ProtocolAnalysisResponse)
async def analyze_protocol_text(request: ProtocolAnalysisRequest):
    """
    Analyze protocol from raw text using LLM parsing
    """
    try:
        parser = get_parser()
        scorer = get_scorer()
        
        # Parse protocol text
        parsed = parser.parse_text(request.protocol_text)
        
        # Score the protocol
        scores = scorer.score_protocol(parsed)
        
        # Generate recommendations if requested
        recommendations = None
        if request.include_recommendations:
            recommender = get_recommender()
            recs = recommender.generate_recommendations(
                parsed, scores, 
                include_pis=True,
                pi_limit=request.recommendation_limit
            )
            recommendations = recs.to_dict()
        
        return ProtocolAnalysisResponse(
            success=True,
            protocol_id=parsed.metadata.protocol_number or "Unknown",
            metadata=parsed.metadata.__dict__,
            eligibility=parsed.eligibility.__dict__,
            study_design=parsed.study_design.__dict__,
            visit_schedule=parsed.visit_schedule.__dict__,
            assessments=parsed.assessments.__dict__,
            safety_monitoring=parsed.safety_monitoring.__dict__,
            endpoints=parsed.endpoints.__dict__,
            sample_size=parsed.sample_size.__dict__,
            scores=scores.to_dict(),
            recommendations=recommendations,
            parsing_confidence=parsed.parsing_confidence,
            parsing_notes=parsed.parsing_notes
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Protocol analysis failed: {str(e)}")


@router.post("/analyze-pdf", response_model=ProtocolAnalysisResponse)
async def analyze_protocol_pdf(
    file: UploadFile = File(..., description="Protocol PDF file"),
    include_recommendations: bool = Form(True),
    recommendation_limit: int = Form(10)
):
    """
    Analyze protocol from uploaded PDF file
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    try:
        parser = get_parser()
        scorer = get_scorer()
        
        # Read PDF bytes
        pdf_bytes = await file.read()
        
        # Parse PDF
        parsed = parser.parse_pdf_bytes(pdf_bytes)
        
        # Score the protocol
        scores = scorer.score_protocol(parsed)
        
        # Generate recommendations if requested
        recommendations = None
        if include_recommendations:
            recommender = get_recommender()
            recs = recommender.generate_recommendations(
                parsed, scores,
                include_pis=True,
                pi_limit=recommendation_limit
            )
            recommendations = recs.to_dict()
        
        return ProtocolAnalysisResponse(
            success=True,
            protocol_id=parsed.metadata.protocol_number or file.filename,
            metadata=parsed.metadata.__dict__,
            eligibility=parsed.eligibility.__dict__,
            study_design=parsed.study_design.__dict__,
            visit_schedule=parsed.visit_schedule.__dict__,
            assessments=parsed.assessments.__dict__,
            safety_monitoring=parsed.safety_monitoring.__dict__,
            endpoints=parsed.endpoints.__dict__,
            sample_size=parsed.sample_size.__dict__,
            scores=scores.to_dict(),
            recommendations=recommendations,
            parsing_confidence=parsed.parsing_confidence,
            parsing_notes=parsed.parsing_notes
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF analysis failed: {str(e)}")


@router.post("/quick-score", response_model=QuickScoreResponse)
async def quick_score_protocol(request: QuickScoreRequest):
    """
    Quick scoring from structured input without PDF parsing
    Useful for feasibility assessments and protocol design
    """
    try:
        from src.protocol_intelligence.parser import (
            ParsedProtocol, ProtocolMetadata, InclusionExclusionCriteria,
            StudyDesign, VisitSchedule, Assessments, SafetyMonitoring,
            Endpoints, SampleSize
        )
        
        scorer = get_scorer()
        
        # Build protocol from structured input
        protocol = ParsedProtocol(
            metadata=ProtocolMetadata(
                phase=request.phase,
                therapeutic_area=request.therapeutic_area,
                indication=request.indication
            ),
            eligibility=InclusionExclusionCriteria(
                inclusion_criteria=["Criterion"] * request.inclusion_criteria_count,
                exclusion_criteria=["Criterion"] * request.exclusion_criteria_count,
                requires_biomarker=request.requires_biomarker,
                requires_prior_therapy=request.requires_prior_therapy
            ),
            study_design=StudyDesign(
                number_of_arms=request.number_of_arms,
                blinding=request.blinding,
                treatment_duration_weeks=request.treatment_duration_weeks,
                adaptive_design=request.adaptive_design,
                dose_escalation=request.dose_escalation
            ),
            visit_schedule=VisitSchedule(
                total_visits=request.total_visits
            ),
            assessments=Assessments(
                imaging_studies=["Imaging"] * request.imaging_modalities,
                pk_sampling=request.pk_sampling,
                pk_timepoints=request.pk_timepoints,
                biopsies_required=request.biopsies_required
            ),
            safety_monitoring=SafetyMonitoring(
                dsmb_required=request.dsmb_required,
                cardiac_monitoring=request.cardiac_monitoring,
                dose_limiting_toxicity=request.dose_escalation
            ),
            sample_size=SampleSize(
                target_enrollment=request.target_enrollment
            )
        )
        
        # Score the protocol
        scores = scorer.score_protocol(protocol)
        
        return QuickScoreResponse(
            success=True,
            overall_complexity=scores.overall_complexity,
            enrollment_difficulty=scores.enrollment_difficulty.to_dict(),
            site_burden=scores.site_burden.to_dict(),
            operational_complexity=scores.operational_complexity.to_dict(),
            amendment_risk=scores.amendment_risk.to_dict(),
            monitoring_complexity=scores.monitoring_complexity.to_dict(),
            patient_burden=scores.patient_burden.to_dict(),
            estimated_enrollment_rate=scores.estimated_enrollment_rate,
            estimated_screen_fail_rate=scores.estimated_screen_fail_rate,
            recommended_site_profile=scores.recommended_site_profile,
            recommended_pi_profile=scores.recommended_pi_profile
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Quick scoring failed: {str(e)}")


@router.get("/sample-analysis")
async def get_sample_analysis():
    """
    Return a sample analysis result for demo purposes
    Uses the NCT01781429 protocol as example
    """
    # Pre-computed sample analysis
    sample_result = {
        "success": True,
        "protocol_id": "BVD-523-01",
        "metadata": {
            "protocol_number": "BVD-523-01",
            "protocol_title": "Phase 1 Dose-Escalation, Safety, Pharmacokinetic and Pharmacodynamic Study of BVD-523 in Patients with Advanced Malignancies",
            "sponsor": "BioMed Valley Discoveries, Inc.",
            "phase": "Phase 1",
            "indication": "Advanced Malignancies",
            "therapeutic_area": "Oncology",
            "drug_name": "BVD-523",
            "version": "Amendment 7",
            "version_date": "11 April 2016"
        },
        "eligibility": {
            "inclusion_criteria_count": 12,
            "exclusion_criteria_count": 13,
            "age_range": {"min": 18, "max": None},
            "requires_biomarker": True,
            "biomarker_details": "Specific genetic mutations required for Part 2",
            "requires_prior_therapy": False
        },
        "study_design": {
            "design_type": "dose-escalation",
            "randomization": False,
            "blinding": "open-label",
            "number_of_arms": 2,
            "dose_escalation": True,
            "adaptive_design": False
        },
        "scores": {
            "overall_complexity": 72.5,
            "enrollment_difficulty": {
                "score": 68.0,
                "factors": [
                    {"name": "Moderate inclusion criteria", "value": 12, "impact": 10},
                    {"name": "Moderate exclusion criteria", "value": 13, "impact": 12},
                    {"name": "Biomarker required", "value": True, "impact": 15},
                    {"name": "Oncology therapeutic area", "value": True, "impact": 10}
                ],
                "recommendations": [
                    "Ensure sites have biomarker testing capabilities or central lab support",
                    "Consider adaptive enrichment design to manage enrollment challenges"
                ]
            },
            "site_burden": {
                "score": 65.0,
                "factors": [
                    {"name": "Multiple imaging modalities", "value": 3, "impact": 15},
                    {"name": "PK sampling required", "value": True, "impact": 15},
                    {"name": "ECG monitoring", "value": True, "impact": 5}
                ],
                "recommendations": [
                    "Consider central imaging review to standardize assessments",
                    "Prioritize experienced sites with dedicated research staff"
                ]
            },
            "operational_complexity": {
                "score": 78.0,
                "factors": [
                    {"name": "Dose escalation", "value": True, "impact": 12},
                    {"name": "Multiple treatment arms", "value": 2, "impact": 5},
                    {"name": "Early phase study", "value": "Phase 1", "impact": 15}
                ],
                "recommendations": [
                    "Ensure 24/7 medical coverage at Phase 1 sites",
                    "Pre-plan dose modification rules to minimize amendments"
                ]
            },
            "amendment_risk": {
                "score": 75.0,
                "factors": [
                    {"name": "Complex eligibility criteria", "value": 25, "impact": 20},
                    {"name": "Dose escalation design", "value": True, "impact": 15},
                    {"name": "Early phase study", "value": "Phase 1", "impact": 15},
                    {"name": "Oncology therapeutic area", "value": True, "impact": 10}
                ],
                "recommendations": [
                    "Build flexibility into site contracts for potential amendments",
                    "Consider protocol optimization review before finalization"
                ]
            },
            "estimated_enrollment_rate": 0.56,
            "estimated_screen_fail_rate": 45.0
        },
        "feasibility_summary": {
            "feasibility_level": "Challenging",
            "feasibility_description": "Protocol is complex and will require careful site selection",
            "recommended_site_count": 15,
            "key_challenges": [
                "Enrollment may be challenging due to strict eligibility criteria",
                "High site burden may limit site participation",
                "Protocol amendments likely during study conduct"
            ]
        }
    }
    
    return sample_result
