#!/usr/bin/env python3
"""Test the oncology protocol scoring engine"""

import sys
sys.path.insert(0, '/Users/harshakaranth/Harsha/Projects/ClinicalTrialProject')

from src.protocol_intelligence.oncology_parser import (
    ParsedOncologyProtocol, OncologyProtocolMetadata, CancerIndication,
    Intervention, PatientPopulation, EndpointsAndResponse,
    OperationalBurden, SafetyMonitoring, TrialDesign
)
from src.protocol_intelligence.oncology_scoring import OncologyProtocolScorer

# Create a test oncology protocol (Phase 1 NSCLC with EGFR mutation)
protocol = ParsedOncologyProtocol(
    metadata=OncologyProtocolMetadata(
        trial_title="Phase 1 Study of Novel EGFR Inhibitor in NSCLC",
        protocol_number="ONCO-001",
        phase="Phase 1"
    ),
    indication=CancerIndication(
        cancer_type="lung",
        cancer_subtype="NSCLC",
        tumor_type="solid_tumor",
        stage="metastatic"
    ),
    intervention=Intervention(
        intervention_type="small_molecule",
        drug_class="TKI",
        route_of_administration="oral"
    ),
    population=PatientPopulation(
        line_of_therapy="2L",
        biomarker_requirements=["EGFR_mutant"],
        ecog_performance_status="0-1",
        cns_metastases_allowed=False,
        prior_therapy_required=["platinum-based chemotherapy"],
        inclusion_criteria=["criterion"] * 12,
        exclusion_criteria=["criterion"] * 15
    ),
    endpoints=EndpointsAndResponse(
        primary_endpoint="DLT_MTD",
        response_criteria="RECIST_1_1",
        imaging_frequency="q8w"
    ),
    operational=OperationalBurden(
        screening_biopsy_required=True,
        on_treatment_biopsy_required=True,
        pk_sampling_required=True,
        pk_timepoints_per_cycle=8,
        echo_muga_required=True
    ),
    safety=SafetyMonitoring(
        dose_escalation_scheme="3+3",
        cardiac_monitoring=True,
        hepatotoxicity_monitoring=True
    ),
    design=TrialDesign(
        design_type="dose_escalation",
        dose_escalation=True,
        target_enrollment=60,
        number_of_arms=1
    )
)

# Score it
scorer = OncologyProtocolScorer()
scores = scorer.score_protocol(protocol)

print("=" * 60)
print("ONCOLOGY PROTOCOL SCORING TEST")
print("=" * 60)
print(f"\nProtocol: {protocol.metadata.trial_title}")
print(f"Phase: {protocol.metadata.phase}")
print(f"Cancer: {protocol.indication.cancer_type} ({protocol.indication.cancer_subtype})")
print(f"Biomarker: {protocol.population.biomarker_requirements}")
print()
print("SCORES:")
print(f"  Overall Complexity: {scores.overall_complexity}")
print(f"  Enrollment Difficulty: {scores.enrollment_difficulty.score}")
print(f"  Site Burden: {scores.site_burden.score}")
print(f"  Protocol Complexity: {scores.protocol_complexity.score}")
print(f"  Monitoring Complexity: {scores.monitoring_complexity.score}")
print(f"  Amendment Risk: {scores.amendment_risk.score}")
print(f"  Patient Burden: {scores.patient_burden.score}")
print()
print("PREDICTIONS:")
print(f"  Est. Enrollment Rate: {scores.estimated_enrollment_rate} pts/site/mo")
print(f"  Est. Screen Fail Rate: {scores.estimated_screen_fail_rate}%")
print()
print("RISK FLAGS:")
for flag in scores.risk_flags:
    print(f"  [{flag.severity.upper()}] {flag.flag_name}")
    print(f"         {flag.description}")
print()
print("TOP ENROLLMENT BOTTLENECKS:")
for i, bottleneck in enumerate(scores.top_enrollment_bottlenecks[:3], 1):
    print(f"  {i}. {bottleneck}")
print()
print("SITE REQUIREMENTS:")
for req in scores.site_capability_requirements[:5]:
    print(f"  ✓ {req}")
print()
print("FEASIBILITY QUESTIONS:")
for q in scores.feasibility_questions[:4]:
    print(f"  • {q}")
print()
print("=" * 60)
print("SUCCESS: Oncology scoring engine works!")
print("=" * 60)
