"""
Oncology Protocol Intelligence API Routes
Specialized endpoints for oncology protocol analysis
"""

import os
from typing import Optional, List
from fastapi import APIRouter, HTTPException, UploadFile, File, Form
from pydantic import BaseModel, Field
from typing import Dict, Any

router = APIRouter(prefix="/oncology-protocol", tags=["Oncology Protocol Intelligence"])


class OncologyQuickScoreRequest(BaseModel):
    """Request for quick oncology protocol scoring"""
    # Basic info
    phase: str = Field("Phase 2", description="Phase 1, 1/2, 2, 3")
    cancer_type: str = Field("lung", description="Cancer type")
    tumor_type: str = Field("solid_tumor", description="solid_tumor or hematologic")
    
    # Intervention
    intervention_type: str = Field("small_molecule", description="small_molecule, immunotherapy, etc.")
    is_combination: bool = Field(False)
    
    # Population
    line_of_therapy: str = Field("2L", description="1L, 2L, 3L+")
    biomarker_required: bool = Field(False)
    biomarker_name: str = Field("", description="e.g., EGFR, HER2+, PD-L1")
    biomarker_prevalence: str = Field("common", description="common (>20%), uncommon (5-20%), rare (<5%)")
    ecog_requirement: str = Field("0-2", description="0-1 or 0-2")
    cns_allowed: bool = Field(True)
    prior_therapy_count: int = Field(1, ge=0)
    inclusion_criteria_count: int = Field(12, ge=0)
    exclusion_criteria_count: int = Field(15, ge=0)
    
    # Operational
    screening_biopsy: bool = Field(False)
    on_treatment_biopsy: bool = Field(False)
    imaging_frequency: str = Field("q8w", description="q6w, q8w, q12w")
    pk_sampling: bool = Field(False)
    echo_required: bool = Field(False)
    
    # Design
    target_enrollment: int = Field(100, ge=1)
    dose_escalation: bool = Field(False)
    number_of_arms: int = Field(1, ge=1)


class OncologyAnalysisResponse(BaseModel):
    """Response from oncology protocol analysis"""
    success: bool
    protocol_id: str
    
    # Parsed data
    metadata: Dict[str, Any]
    indication: Dict[str, Any]
    intervention: Dict[str, Any]
    population: Dict[str, Any]
    endpoints: Dict[str, Any]
    operational: Dict[str, Any]
    safety: Dict[str, Any]
    design: Dict[str, Any]
    
    # Scores
    scores: Dict[str, Any]
    
    # Risk analysis
    risk_flags: List[Dict[str, Any]]
    top_enrollment_bottlenecks: List[str]
    site_capability_requirements: List[str]
    feasibility_questions: List[str]
    
    # Predictions
    estimated_screen_fail_rate: float
    estimated_enrollment_rate: float
    
    # Site matching
    site_matching_criteria: Dict[str, Any]
    
    parsing_confidence: float
    parsing_notes: List[str]


def get_oncology_parser():
    """Get oncology protocol parser"""
    from src.protocol_intelligence.oncology_parser import OncologyProtocolParser
    return OncologyProtocolParser()


def get_oncology_scorer():
    """Get oncology protocol scorer"""
    from src.protocol_intelligence.oncology_scoring import OncologyProtocolScorer
    return OncologyProtocolScorer()


@router.post("/analyze-pdf", response_model=OncologyAnalysisResponse)
async def analyze_oncology_pdf(
    file: UploadFile = File(..., description="Oncology protocol PDF"),
):
    """
    Analyze an oncology protocol PDF using LLM extraction
    """
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="File must be a PDF")
    
    try:
        print(f"\n{'='*60}")
        print(f"[ONCOLOGY] Starting PDF analysis for: {file.filename}")
        print(f"{'='*60}")
        
        parser = get_oncology_parser()
        scorer = get_oncology_scorer()
        
        # Read and parse PDF
        pdf_bytes = await file.read()
        print(f"[ONCOLOGY] PDF size: {len(pdf_bytes):,} bytes")
        
        # Extract text first to debug
        import fitz
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        print(f"[ONCOLOGY] PDF pages: {len(doc)}")
        
        sample_text = ""
        for i in range(min(3, len(doc))):
            sample_text += doc[i].get_text()
        doc.close()
        
        print(f"[ONCOLOGY] Extracted text length: {len(sample_text):,} chars")
        print(f"[ONCOLOGY] First 500 chars of PDF text:")
        print("-" * 40)
        print(sample_text[:500])
        print("-" * 40)
        
        # Now parse with LLM
        print(f"[ONCOLOGY] Sending to LLM for parsing...")
        protocol = parser.parse_pdf_bytes(pdf_bytes)
        
        print(f"\n[ONCOLOGY] === PARSED DATA ===")
        print(f"[ONCOLOGY] Title: {protocol.metadata.trial_title or 'EMPTY'}")
        print(f"[ONCOLOGY] Protocol #: {protocol.metadata.protocol_number or 'EMPTY'}")
        print(f"[ONCOLOGY] Phase: {protocol.metadata.phase or 'EMPTY'}")
        print(f"[ONCOLOGY] Sponsor: {protocol.metadata.sponsor or 'EMPTY'}")
        print(f"[ONCOLOGY] Cancer Type: {protocol.indication.cancer_type or 'EMPTY'}")
        print(f"[ONCOLOGY] Tumor Type: {protocol.indication.tumor_type or 'EMPTY'}")
        print(f"[ONCOLOGY] Drug Name: {protocol.intervention.drug_name or 'EMPTY'}")
        print(f"[ONCOLOGY] Line of Therapy: {protocol.population.line_of_therapy or 'EMPTY'}")
        print(f"[ONCOLOGY] Biomarkers: {protocol.population.biomarker_requirements or 'EMPTY'}")
        print(f"[ONCOLOGY] Primary Endpoint: {protocol.endpoints.primary_endpoint or 'EMPTY'}")
        print(f"[ONCOLOGY] Target Enrollment: {protocol.design.target_enrollment or 'EMPTY'}")
        print(f"[ONCOLOGY] Parsing Confidence: {protocol.parsing_confidence}")
        print(f"[ONCOLOGY] Parsing Notes: {protocol.parsing_notes}")
        print(f"[ONCOLOGY] ===================\n")
        
        # Score the protocol
        scores = scorer.score_protocol(protocol)
        
        # Debug: Print scoring results
        print(f"\n[ONCOLOGY] === SCORING RESULTS ===")
        print(f"[ONCOLOGY] Overall Complexity: {scores.overall_complexity}")
        print(f"[ONCOLOGY] Enrollment Difficulty: {scores.enrollment_difficulty.score}")
        print(f"[ONCOLOGY] Est. Screen Fail Rate: {scores.estimated_screen_fail_rate}%")
        print(f"[ONCOLOGY] Est. Enrollment Rate: {scores.estimated_enrollment_rate} pts/site/mo")
        print(f"\n[ONCOLOGY] RISK FLAGS ({len(scores.risk_flags)}):")
        for rf in scores.risk_flags:
            print(f"  [{rf.severity.upper()}] {rf.flag_name}: {rf.description}")
        print(f"\n[ONCOLOGY] SITE REQUIREMENTS ({len(scores.site_capability_requirements)}):")
        for req in scores.site_capability_requirements:
            print(f"  ✓ {req}")
        print(f"\n[ONCOLOGY] ENROLLMENT BOTTLENECKS ({len(scores.top_enrollment_bottlenecks)}):")
        for bn in scores.top_enrollment_bottlenecks:
            print(f"  • {bn}")
        print(f"\n[ONCOLOGY] FEASIBILITY QUESTIONS ({len(scores.feasibility_questions)}):")
        for q in scores.feasibility_questions:
            print(f"  ? {q}")
        print(f"[ONCOLOGY] ========================\n")
        
        return OncologyAnalysisResponse(
            success=True,
            protocol_id=protocol.metadata.protocol_number or file.filename,
            metadata=protocol.metadata.__dict__,
            indication=protocol.indication.__dict__,
            intervention=protocol.intervention.__dict__,
            population={
                **protocol.population.__dict__,
                "inclusion_criteria_count": len(protocol.population.inclusion_criteria or []),
                "exclusion_criteria_count": len(protocol.population.exclusion_criteria or [])
            },
            endpoints=protocol.endpoints.__dict__,
            operational=protocol.operational.__dict__,
            safety=protocol.safety.__dict__,
            design=protocol.design.__dict__,
            scores={
                "overall_complexity": scores.overall_complexity,
                "enrollment_difficulty": scores.enrollment_difficulty.to_dict(),
                "site_burden": scores.site_burden.to_dict(),
                "protocol_complexity": scores.protocol_complexity.to_dict(),
                "monitoring_complexity": scores.monitoring_complexity.to_dict(),
                "amendment_risk": scores.amendment_risk.to_dict(),
                "patient_burden": scores.patient_burden.to_dict()
            },
            risk_flags=[{
                "flag_name": rf.flag_name,
                "severity": rf.severity,
                "description": rf.description,
                "mitigation": rf.mitigation
            } for rf in scores.risk_flags],
            top_enrollment_bottlenecks=scores.top_enrollment_bottlenecks,
            site_capability_requirements=scores.site_capability_requirements,
            feasibility_questions=scores.feasibility_questions,
            estimated_screen_fail_rate=scores.estimated_screen_fail_rate,
            estimated_enrollment_rate=scores.estimated_enrollment_rate,
            site_matching_criteria=scores.site_matching_criteria,
            parsing_confidence=protocol.parsing_confidence,
            parsing_notes=protocol.parsing_notes
        )
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"PDF analysis failed: {str(e)}")


@router.post("/quick-score")
async def quick_score_oncology(request: OncologyQuickScoreRequest):
    """
    Quick scoring from structured input - no PDF parsing needed
    """
    try:
        from src.protocol_intelligence.oncology_parser import (
            ParsedOncologyProtocol, OncologyProtocolMetadata, CancerIndication,
            Intervention, PatientPopulation, EndpointsAndResponse,
            OperationalBurden, SafetyMonitoring, TrialDesign
        )
        
        scorer = get_oncology_scorer()
        
        # Build protocol from form input
        protocol = ParsedOncologyProtocol(
            metadata=OncologyProtocolMetadata(
                phase=request.phase
            ),
            indication=CancerIndication(
                cancer_type=request.cancer_type,
                tumor_type=request.tumor_type
            ),
            intervention=Intervention(
                intervention_type=request.intervention_type,
                combination_agents=["agent"] if request.is_combination else []
            ),
            population=PatientPopulation(
                line_of_therapy=request.line_of_therapy,
                biomarker_requirements=[request.biomarker_name] if request.biomarker_required and request.biomarker_name else [],
                ecog_performance_status=request.ecog_requirement,
                cns_metastases_allowed=request.cns_allowed,
                prior_therapy_required=["therapy"] * request.prior_therapy_count if request.prior_therapy_count > 0 else [],
                inclusion_criteria=["criterion"] * request.inclusion_criteria_count,
                exclusion_criteria=["criterion"] * request.exclusion_criteria_count
            ),
            endpoints=EndpointsAndResponse(
                imaging_frequency=request.imaging_frequency
            ),
            operational=OperationalBurden(
                screening_biopsy_required=request.screening_biopsy,
                on_treatment_biopsy_required=request.on_treatment_biopsy,
                pk_sampling_required=request.pk_sampling,
                echo_muga_required=request.echo_required
            ),
            safety=SafetyMonitoring(
                irae_monitoring="immunotherapy" in request.intervention_type.lower()
            ),
            design=TrialDesign(
                target_enrollment=request.target_enrollment,
                dose_escalation=request.dose_escalation,
                number_of_arms=request.number_of_arms
            )
        )
        
        # Score
        scores = scorer.score_protocol(protocol)
        
        return {
            "success": True,
            "overall_complexity": scores.overall_complexity,
            "scores": {
                "enrollment_difficulty": scores.enrollment_difficulty.to_dict(),
                "site_burden": scores.site_burden.to_dict(),
                "protocol_complexity": scores.protocol_complexity.to_dict(),
                "monitoring_complexity": scores.monitoring_complexity.to_dict(),
                "amendment_risk": scores.amendment_risk.to_dict(),
                "patient_burden": scores.patient_burden.to_dict()
            },
            "risk_flags": [{
                "flag_name": rf.flag_name,
                "severity": rf.severity,
                "description": rf.description,
                "mitigation": rf.mitigation
            } for rf in scores.risk_flags],
            "top_enrollment_bottlenecks": scores.top_enrollment_bottlenecks,
            "site_capability_requirements": scores.site_capability_requirements,
            "feasibility_questions": scores.feasibility_questions,
            "estimated_screen_fail_rate": scores.estimated_screen_fail_rate,
            "estimated_enrollment_rate": scores.estimated_enrollment_rate,
            "site_matching_criteria": scores.site_matching_criteria
        }
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Quick scoring failed: {str(e)}")


@router.get("/sample-analysis")
async def get_sample_oncology_analysis():
    """
    Return a sample oncology protocol analysis for demo
    Based on the BVD-523 Phase 1 oncology protocol
    """
    return {
        "success": True,
        "protocol_id": "BVD-523-01",
        "metadata": {
            "trial_title": "Phase 1 Dose-Escalation, Safety, Pharmacokinetic and Pharmacodynamic Study of BVD-523 in Patients with Advanced Malignancies",
            "protocol_number": "BVD-523-01",
            "sponsor": "BioMed Valley Discoveries, Inc.",
            "phase": "Phase 1",
            "version": "Amendment 7",
            "version_date": "11 April 2016"
        },
        "indication": {
            "cancer_type": "solid_tumor",
            "cancer_subtype": "Advanced malignancies with MAPK pathway mutations",
            "tumor_type": "solid_tumor",
            "histology": "various",
            "stage": "metastatic"
        },
        "intervention": {
            "intervention_type": "small_molecule",
            "drug_name": "BVD-523",
            "drug_class": "ERK inhibitor",
            "mechanism_of_action": "ERK1/2 inhibition",
            "route_of_administration": "oral",
            "dosing_schedule": "BID continuous",
            "combination_agents": []
        },
        "population": {
            "line_of_therapy": "any",
            "biomarker_requirements": ["MAPK pathway mutation (BRAF, NRAS, KRAS)"],
            "ecog_performance_status": "0-1",
            "cns_metastases_allowed": True,
            "cns_metastases_conditions": "Stable, treated CNS metastases allowed",
            "inclusion_criteria_count": 12,
            "exclusion_criteria_count": 13
        },
        "endpoints": {
            "primary_endpoint": "DLT_MTD",
            "primary_endpoint_definition": "Determine MTD and RP2D",
            "secondary_endpoints": ["PK profile", "Tumor response (RECIST 1.1)"],
            "response_criteria": "RECIST_1_1",
            "imaging_frequency": "q8w"
        },
        "operational": {
            "screening_biopsy_required": False,
            "on_treatment_biopsy_required": True,
            "pk_sampling_required": True,
            "pk_timepoints_per_cycle": 12,
            "echo_muga_required": True,
            "central_lab_required": True
        },
        "design": {
            "design_type": "dose_escalation",
            "dose_escalation": True,
            "number_of_arms": 2,
            "expansion_cohorts": ["BRAF mutant melanoma", "BRAF mutant CRC", "NRAS mutant melanoma"],
            "target_enrollment": 150
        },
        "scores": {
            "overall_complexity": 68.5,
            "enrollment_difficulty": {
                "score": 72.0,
                "factors": [
                    {"name": "Biomarker requirement (MAPK mutations)", "value": "15-20% prevalence", "impact": 15},
                    {"name": "On-treatment biopsy required", "value": True, "impact": 15},
                    {"name": "Strict ECOG (0-1)", "value": "0-1", "impact": 5}
                ],
                "recommendations": [
                    "Partner with sites that have high-volume molecular testing programs",
                    "Consider central biomarker testing to maximize screening efficiency"
                ]
            },
            "site_burden": {
                "score": 65.0,
                "factors": [
                    {"name": "Intensive PK sampling", "value": 12, "impact": 15},
                    {"name": "On-treatment biopsy required", "value": True, "impact": 15},
                    {"name": "ECHO/MUGA required", "value": True, "impact": 8}
                ],
                "recommendations": [
                    "Ensure sites have interventional radiology support",
                    "Consider sparse PK sampling to reduce burden"
                ]
            },
            "protocol_complexity": {
                "score": 75.0,
                "factors": [
                    {"name": "Phase 1 study", "value": "Phase 1", "impact": 15},
                    {"name": "Dose escalation", "value": True, "impact": 10},
                    {"name": "Multiple expansion cohorts", "value": 3, "impact": 8}
                ],
                "recommendations": [
                    "Ensure 24/7 medical coverage for DLT assessment",
                    "Stagger cohort activation to manage site workload"
                ]
            },
            "monitoring_complexity": {
                "score": 58.0,
                "factors": [
                    {"name": "Dose escalation scheme", "value": "3+3", "impact": 8},
                    {"name": "Cardiac monitoring", "value": True, "impact": 10}
                ],
                "recommendations": []
            },
            "amendment_risk": {
                "score": 70.0,
                "factors": [
                    {"name": "Early phase study", "value": "Phase 1", "impact": 15},
                    {"name": "Dose escalation design", "value": True, "impact": 12}
                ],
                "recommendations": [
                    "Build amendment flexibility into site contracts",
                    "Pre-define dose modification rules"
                ]
            },
            "patient_burden": {
                "score": 55.0,
                "factors": [
                    {"name": "On-treatment biopsy", "value": True, "impact": 15},
                    {"name": "Intensive blood draws", "value": 12, "impact": 10}
                ],
                "recommendations": [
                    "Provide clear patient education on biopsy procedures"
                ]
            }
        },
        "risk_flags": [
            {
                "flag_name": "Mandatory On-Treatment Biopsy",
                "severity": "medium",
                "description": "On-treatment biopsies increase patient burden and screen failures",
                "mitigation": "Consider making biopsies optional or limiting to accessible lesions"
            },
            {
                "flag_name": "Phase 1 with Multiple Expansions",
                "severity": "medium",
                "description": "Multiple expansion cohorts increase operational complexity",
                "mitigation": "Stagger cohort activation to manage site workload"
            },
            {
                "flag_name": "Uncommon Biomarker",
                "severity": "medium",
                "description": "MAPK pathway mutations have 15-20% prevalence",
                "mitigation": "Ensure robust screening program with central testing"
            }
        ],
        "top_enrollment_bottlenecks": [
            "Biomarker requirement (MAPK mutations) limits eligible population to ~15-20%",
            "On-treatment biopsy requirement may cause 10-15% additional screen failures",
            "ECOG 0-1 requirement excludes patients with declining status"
        ],
        "site_capability_requirements": [
            "Phase 1 unit or equivalent with 24/7 coverage",
            "Molecular pathology for MAPK mutation testing",
            "Interventional radiology for tumor biopsies",
            "Cardiology support for cardiac monitoring"
        ],
        "feasibility_questions": [
            "How many patients with MAPK pathway mutations do you see per month?",
            "Do you have NGS testing in-house or use a reference lab?",
            "Do you have IR support for research biopsies?",
            "Do you have a dedicated Phase 1 unit?",
            "What is your DLT reporting process?",
            "What competing trials are currently enrolling in this space?"
        ],
        "estimated_screen_fail_rate": 45.0,
        "estimated_enrollment_rate": 0.5,
        "site_matching_criteria": {
            "therapeutic_area": "oncology",
            "cancer_type": "solid_tumor",
            "phase": "Phase 1",
            "required_capabilities": ["molecular_testing", "interventional_radiology", "phase_1_unit"],
            "minimum_experience": {"oncology_trials": 5, "phase_specific": 3}
        },
        "parsing_confidence": 0.92,
        "parsing_notes": []
    }
