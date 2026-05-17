#!/usr/bin/env python3
"""Quick test of the protocol scoring engine"""

import sys
sys.path.insert(0, '/Users/harshakaranth/Harsha/Projects/ClinicalTrialProject')

from src.protocol_intelligence.parser import (
    ParsedProtocol, ProtocolMetadata, InclusionExclusionCriteria, 
    StudyDesign, VisitSchedule, Assessments, SafetyMonitoring, SampleSize
)
from src.protocol_intelligence.scoring import ProtocolScorer

# Create a test protocol
protocol = ParsedProtocol(
    metadata=ProtocolMetadata(
        protocol_number="TEST-001",
        phase="Phase 2",
        therapeutic_area="Oncology",
        indication="Breast Cancer"
    ),
    eligibility=InclusionExclusionCriteria(
        inclusion_criteria=["Criterion " + str(i) for i in range(12)],
        exclusion_criteria=["Exclusion " + str(i) for i in range(10)],
        requires_biomarker=True
    ),
    study_design=StudyDesign(
        number_of_arms=2,
        blinding="double-blind",
        treatment_duration_weeks=24
    ),
    visit_schedule=VisitSchedule(total_visits=15),
    assessments=Assessments(
        imaging_studies=["CT", "MRI"],
        pk_sampling=True,
        pk_timepoints=8
    ),
    safety_monitoring=SafetyMonitoring(dsmb_required=True, cardiac_monitoring=True),
    sample_size=SampleSize(target_enrollment=200)
)

scorer = ProtocolScorer()
scores = scorer.score_protocol(protocol)

print("=== Protocol Scoring Test ===")
print(f"Overall Complexity: {scores.overall_complexity}")
print(f"Enrollment Difficulty: {scores.enrollment_difficulty.score}")
print(f"Site Burden: {scores.site_burden.score}")
print(f"Operational Complexity: {scores.operational_complexity.score}")
print(f"Est. Enrollment Rate: {scores.estimated_enrollment_rate} pts/site/mo")
print(f"Est. Screen Fail Rate: {scores.estimated_screen_fail_rate}%")
print("\nSUCCESS: Scoring engine works!")
