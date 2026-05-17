"""
Protocol Scoring Engine
Computes operational complexity, burden, and risk scores from parsed protocols
"""

from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict
from .parser import ParsedProtocol


@dataclass
class ScoreBreakdown:
    """Detailed breakdown of a score"""
    score: float  # 0-100
    factors: List[Dict[str, Any]]  # Contributing factors with weights
    recommendations: List[str]  # Actionable recommendations
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProtocolScores:
    """Complete scoring output for a protocol"""
    overall_complexity: float  # 0-100
    enrollment_difficulty: ScoreBreakdown
    site_burden: ScoreBreakdown
    operational_complexity: ScoreBreakdown
    amendment_risk: ScoreBreakdown
    monitoring_complexity: ScoreBreakdown
    patient_burden: ScoreBreakdown
    
    # Summary metrics
    estimated_enrollment_rate: float  # patients per site per month
    estimated_screen_fail_rate: float  # percentage
    recommended_site_profile: Dict[str, Any]
    recommended_pi_profile: Dict[str, Any]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_complexity": self.overall_complexity,
            "enrollment_difficulty": self.enrollment_difficulty.to_dict(),
            "site_burden": self.site_burden.to_dict(),
            "operational_complexity": self.operational_complexity.to_dict(),
            "amendment_risk": self.amendment_risk.to_dict(),
            "monitoring_complexity": self.monitoring_complexity.to_dict(),
            "patient_burden": self.patient_burden.to_dict(),
            "estimated_enrollment_rate": self.estimated_enrollment_rate,
            "estimated_screen_fail_rate": self.estimated_screen_fail_rate,
            "recommended_site_profile": self.recommended_site_profile,
            "recommended_pi_profile": self.recommended_pi_profile
        }


class ProtocolScorer:
    """
    Computes operational scores for clinical trial protocols
    Based on industry benchmarks and operational complexity factors
    """
    
    # Therapeutic area complexity multipliers
    THERAPEUTIC_AREA_COMPLEXITY = {
        "oncology": 1.4,
        "neurology": 1.3,
        "cardiology": 1.2,
        "immunology": 1.2,
        "rare_disease": 1.5,
        "pediatrics": 1.3,
        "psychiatry": 1.1,
        "infectious_disease": 1.0,
        "dermatology": 0.9,
        "gastroenterology": 1.0,
        "endocrinology": 1.0,
        "respiratory": 1.0,
        "default": 1.0
    }
    
    # Phase complexity multipliers
    PHASE_COMPLEXITY = {
        "phase 1": 1.3,
        "phase 1/2": 1.25,
        "phase 2": 1.0,
        "phase 2/3": 1.1,
        "phase 3": 1.15,
        "phase 4": 0.9,
        "default": 1.0
    }
    
    def __init__(self):
        pass
    
    def _get_ta_multiplier(self, therapeutic_area: str) -> float:
        """Get therapeutic area complexity multiplier"""
        ta_lower = therapeutic_area.lower() if therapeutic_area else ""
        for key, value in self.THERAPEUTIC_AREA_COMPLEXITY.items():
            if key in ta_lower:
                return value
        return self.THERAPEUTIC_AREA_COMPLEXITY["default"]
    
    def _get_phase_multiplier(self, phase: str) -> float:
        """Get phase complexity multiplier"""
        phase_lower = phase.lower() if phase else ""
        for key, value in self.PHASE_COMPLEXITY.items():
            if key in phase_lower:
                return value
        return self.PHASE_COMPLEXITY["default"]
    
    def _score_enrollment_difficulty(self, protocol: ParsedProtocol) -> ScoreBreakdown:
        """
        Score enrollment difficulty based on eligibility criteria
        Higher score = more difficult to enroll
        """
        factors = []
        base_score = 30  # Baseline
        
        # Number of inclusion criteria
        n_inclusion = len(protocol.eligibility.inclusion_criteria)
        if n_inclusion > 15:
            factor_score = 15
            factors.append({"name": "Many inclusion criteria", "value": n_inclusion, "impact": factor_score})
        elif n_inclusion > 10:
            factor_score = 10
            factors.append({"name": "Moderate inclusion criteria", "value": n_inclusion, "impact": factor_score})
        else:
            factor_score = 5
            factors.append({"name": "Few inclusion criteria", "value": n_inclusion, "impact": factor_score})
        base_score += factor_score
        
        # Number of exclusion criteria
        n_exclusion = len(protocol.eligibility.exclusion_criteria)
        if n_exclusion > 20:
            factor_score = 20
            factors.append({"name": "Many exclusion criteria", "value": n_exclusion, "impact": factor_score})
        elif n_exclusion > 12:
            factor_score = 12
            factors.append({"name": "Moderate exclusion criteria", "value": n_exclusion, "impact": factor_score})
        else:
            factor_score = 5
            factors.append({"name": "Few exclusion criteria", "value": n_exclusion, "impact": factor_score})
        base_score += factor_score
        
        # Biomarker requirement
        if protocol.eligibility.requires_biomarker:
            factor_score = 15
            factors.append({"name": "Biomarker required", "value": True, "impact": factor_score})
            base_score += factor_score
        
        # Prior therapy requirement
        if protocol.eligibility.requires_prior_therapy:
            factor_score = 10
            factors.append({"name": "Prior therapy required", "value": True, "impact": factor_score})
            base_score += factor_score
        
        # Age restrictions
        age_range = protocol.eligibility.age_range or {}
        if age_range.get("min", 18) > 18 or age_range.get("max"):
            factor_score = 5
            factors.append({"name": "Age restrictions", "value": age_range, "impact": factor_score})
            base_score += factor_score
        
        # Apply therapeutic area multiplier
        ta_mult = self._get_ta_multiplier(protocol.metadata.therapeutic_area)
        base_score = min(100, base_score * ta_mult)
        
        # Generate recommendations
        recommendations = []
        if n_inclusion > 12:
            recommendations.append("Consider consolidating inclusion criteria to improve enrollment")
        if n_exclusion > 15:
            recommendations.append("Review exclusion criteria for potential relaxation")
        if protocol.eligibility.requires_biomarker:
            recommendations.append("Ensure sites have biomarker testing capabilities or central lab support")
        if base_score > 70:
            recommendations.append("Consider adaptive enrichment design to manage enrollment challenges")
        
        return ScoreBreakdown(
            score=round(base_score, 1),
            factors=factors,
            recommendations=recommendations
        )
    
    def _score_site_burden(self, protocol: ParsedProtocol) -> ScoreBreakdown:
        """
        Score operational burden on sites
        Higher score = more burdensome
        """
        factors = []
        base_score = 20
        
        # Visit frequency
        total_visits = protocol.visit_schedule.total_visits
        if total_visits > 20:
            factor_score = 20
            factors.append({"name": "High visit count", "value": total_visits, "impact": factor_score})
        elif total_visits > 10:
            factor_score = 12
            factors.append({"name": "Moderate visit count", "value": total_visits, "impact": factor_score})
        else:
            factor_score = 5
            factors.append({"name": "Low visit count", "value": total_visits, "impact": factor_score})
        base_score += factor_score
        
        # Lab tests
        n_labs = len(protocol.assessments.lab_tests)
        if n_labs > 10:
            factor_score = 15
            factors.append({"name": "Many lab tests", "value": n_labs, "impact": factor_score})
        elif n_labs > 5:
            factor_score = 8
            factors.append({"name": "Moderate lab tests", "value": n_labs, "impact": factor_score})
        base_score += factor_score if n_labs > 5 else 0
        
        # Imaging studies
        n_imaging = len(protocol.assessments.imaging_studies)
        if n_imaging > 3:
            factor_score = 15
            factors.append({"name": "Multiple imaging modalities", "value": n_imaging, "impact": factor_score})
            base_score += factor_score
        elif n_imaging > 0:
            factor_score = 8
            factors.append({"name": "Imaging required", "value": n_imaging, "impact": factor_score})
            base_score += factor_score
        
        # PK sampling
        if protocol.assessments.pk_sampling:
            pk_points = protocol.assessments.pk_timepoints
            if pk_points > 10:
                factor_score = 15
                factors.append({"name": "Intensive PK sampling", "value": pk_points, "impact": factor_score})
            else:
                factor_score = 8
                factors.append({"name": "PK sampling required", "value": pk_points, "impact": factor_score})
            base_score += factor_score
        
        # Biopsies
        if protocol.assessments.biopsies_required:
            factor_score = 12
            factors.append({"name": "Biopsies required", "value": protocol.assessments.biopsy_count, "impact": factor_score})
            base_score += factor_score
        
        # Special equipment
        n_equipment = len(protocol.assessments.special_equipment)
        if n_equipment > 0:
            factor_score = 10
            factors.append({"name": "Special equipment needed", "value": n_equipment, "impact": factor_score})
            base_score += factor_score
        
        # ECG requirements
        if protocol.assessments.ecg_required:
            factor_score = 5
            factors.append({"name": "ECG monitoring", "value": True, "impact": factor_score})
            base_score += factor_score
        
        base_score = min(100, base_score)
        
        recommendations = []
        if total_visits > 15:
            recommendations.append("Consider telemedicine for non-critical visits to reduce site burden")
        if protocol.assessments.pk_sampling and protocol.assessments.pk_timepoints > 8:
            recommendations.append("Evaluate sparse PK sampling strategy to reduce patient/site burden")
        if n_imaging > 2:
            recommendations.append("Consider central imaging review to standardize assessments")
        if base_score > 60:
            recommendations.append("Prioritize experienced sites with dedicated research staff")
        
        return ScoreBreakdown(
            score=round(base_score, 1),
            factors=factors,
            recommendations=recommendations
        )
    
    def _score_operational_complexity(self, protocol: ParsedProtocol) -> ScoreBreakdown:
        """
        Score overall operational complexity
        """
        factors = []
        base_score = 25
        
        # Study design complexity
        if protocol.study_design.adaptive_design:
            factor_score = 15
            factors.append({"name": "Adaptive design", "value": True, "impact": factor_score})
            base_score += factor_score
        
        if protocol.study_design.dose_escalation:
            factor_score = 12
            factors.append({"name": "Dose escalation", "value": True, "impact": factor_score})
            base_score += factor_score
        
        # Number of arms
        n_arms = protocol.study_design.number_of_arms
        if n_arms > 3:
            factor_score = 12
            factors.append({"name": "Multiple treatment arms", "value": n_arms, "impact": factor_score})
            base_score += factor_score
        elif n_arms > 1:
            factor_score = 5
            factors.append({"name": "Multiple arms", "value": n_arms, "impact": factor_score})
            base_score += factor_score
        
        # Blinding complexity
        blinding = protocol.study_design.blinding.lower() if protocol.study_design.blinding else ""
        if "double" in blinding or "triple" in blinding:
            factor_score = 10
            factors.append({"name": "Double/triple blind", "value": blinding, "impact": factor_score})
            base_score += factor_score
        
        # Treatment duration
        duration = protocol.study_design.treatment_duration_weeks
        if duration > 52:
            factor_score = 15
            factors.append({"name": "Long treatment duration", "value": f"{duration} weeks", "impact": factor_score})
            base_score += factor_score
        elif duration > 24:
            factor_score = 8
            factors.append({"name": "Moderate treatment duration", "value": f"{duration} weeks", "impact": factor_score})
            base_score += factor_score
        
        # Phase multiplier
        phase_mult = self._get_phase_multiplier(protocol.metadata.phase)
        base_score = min(100, base_score * phase_mult)
        
        recommendations = []
        if protocol.study_design.adaptive_design:
            recommendations.append("Ensure statistical expertise for adaptive design implementation")
        if n_arms > 2:
            recommendations.append("Consider centralized randomization system")
        if duration > 52:
            recommendations.append("Plan for patient retention strategies over long treatment period")
        
        return ScoreBreakdown(
            score=round(base_score, 1),
            factors=factors,
            recommendations=recommendations
        )
    
    def _score_amendment_risk(self, protocol: ParsedProtocol) -> ScoreBreakdown:
        """
        Predict likelihood of protocol amendments based on complexity factors
        """
        factors = []
        base_score = 20
        
        # Complex eligibility = higher amendment risk
        n_criteria = len(protocol.eligibility.inclusion_criteria) + len(protocol.eligibility.exclusion_criteria)
        if n_criteria > 25:
            factor_score = 20
            factors.append({"name": "Complex eligibility criteria", "value": n_criteria, "impact": factor_score})
            base_score += factor_score
        elif n_criteria > 15:
            factor_score = 10
            factors.append({"name": "Moderate eligibility complexity", "value": n_criteria, "impact": factor_score})
            base_score += factor_score
        
        # Dose escalation studies have higher amendment rates
        if protocol.study_design.dose_escalation:
            factor_score = 15
            factors.append({"name": "Dose escalation design", "value": True, "impact": factor_score})
            base_score += factor_score
        
        # Early phase = higher amendment risk
        phase = protocol.metadata.phase.lower() if protocol.metadata.phase else ""
        if "1" in phase:
            factor_score = 15
            factors.append({"name": "Early phase study", "value": protocol.metadata.phase, "impact": factor_score})
            base_score += factor_score
        
        # Many endpoints = higher amendment risk
        n_endpoints = (len(protocol.endpoints.primary_endpoints) + 
                      len(protocol.endpoints.secondary_endpoints))
        if n_endpoints > 10:
            factor_score = 12
            factors.append({"name": "Many endpoints", "value": n_endpoints, "impact": factor_score})
            base_score += factor_score
        
        # Oncology has higher amendment rates
        ta = protocol.metadata.therapeutic_area.lower() if protocol.metadata.therapeutic_area else ""
        if "oncology" in ta or "cancer" in ta:
            factor_score = 10
            factors.append({"name": "Oncology therapeutic area", "value": True, "impact": factor_score})
            base_score += factor_score
        
        base_score = min(100, base_score)
        
        recommendations = []
        if base_score > 60:
            recommendations.append("Build flexibility into site contracts for potential amendments")
            recommendations.append("Consider protocol optimization review before finalization")
        if protocol.study_design.dose_escalation:
            recommendations.append("Pre-plan dose modification rules to minimize amendments")
        
        return ScoreBreakdown(
            score=round(base_score, 1),
            factors=factors,
            recommendations=recommendations
        )
    
    def _score_monitoring_complexity(self, protocol: ParsedProtocol) -> ScoreBreakdown:
        """
        Score monitoring and safety oversight complexity
        """
        factors = []
        base_score = 20
        
        # DSMB requirement
        if protocol.safety_monitoring.dsmb_required:
            factor_score = 15
            factors.append({"name": "DSMB required", "value": True, "impact": factor_score})
            base_score += factor_score
        
        # Interim analyses
        n_interim = protocol.safety_monitoring.interim_analyses
        if n_interim > 2:
            factor_score = 12
            factors.append({"name": "Multiple interim analyses", "value": n_interim, "impact": factor_score})
            base_score += factor_score
        elif n_interim > 0:
            factor_score = 6
            factors.append({"name": "Interim analysis planned", "value": n_interim, "impact": factor_score})
            base_score += factor_score
        
        # Safety monitoring requirements
        safety_monitors = sum([
            protocol.safety_monitoring.cardiac_monitoring,
            protocol.safety_monitoring.liver_monitoring,
            protocol.safety_monitoring.renal_monitoring,
            protocol.safety_monitoring.cns_monitoring
        ])
        if safety_monitors >= 3:
            factor_score = 15
            factors.append({"name": "Multiple organ monitoring", "value": safety_monitors, "impact": factor_score})
            base_score += factor_score
        elif safety_monitors > 0:
            factor_score = 8
            factors.append({"name": "Organ-specific monitoring", "value": safety_monitors, "impact": factor_score})
            base_score += factor_score
        
        # DLT assessment (Phase 1)
        if protocol.safety_monitoring.dose_limiting_toxicity:
            factor_score = 12
            factors.append({"name": "DLT assessment", "value": True, "impact": factor_score})
            base_score += factor_score
        
        # Special safety concerns
        n_concerns = len(protocol.safety_monitoring.special_safety_concerns)
        if n_concerns > 3:
            factor_score = 10
            factors.append({"name": "Multiple safety concerns", "value": n_concerns, "impact": factor_score})
            base_score += factor_score
        
        base_score = min(100, base_score)
        
        recommendations = []
        if protocol.safety_monitoring.dsmb_required:
            recommendations.append("Establish DSMB charter and meeting schedule early")
        if safety_monitors >= 2:
            recommendations.append("Consider centralized safety monitoring dashboard")
        if base_score > 60:
            recommendations.append("Ensure medical monitor availability for rapid safety reviews")
        
        return ScoreBreakdown(
            score=round(base_score, 1),
            factors=factors,
            recommendations=recommendations
        )
    
    def _score_patient_burden(self, protocol: ParsedProtocol) -> ScoreBreakdown:
        """
        Score burden on patients participating in the trial
        """
        factors = []
        base_score = 20
        
        # Visit frequency
        total_visits = protocol.visit_schedule.total_visits
        if total_visits > 20:
            factor_score = 20
            factors.append({"name": "High visit frequency", "value": total_visits, "impact": factor_score})
        elif total_visits > 12:
            factor_score = 12
            factors.append({"name": "Moderate visit frequency", "value": total_visits, "impact": factor_score})
        else:
            factor_score = 5
            factors.append({"name": "Manageable visit frequency", "value": total_visits, "impact": factor_score})
        base_score += factor_score
        
        # Treatment duration
        duration = protocol.study_design.treatment_duration_weeks
        if duration > 52:
            factor_score = 15
            factors.append({"name": "Long treatment duration", "value": f"{duration} weeks", "impact": factor_score})
            base_score += factor_score
        elif duration > 24:
            factor_score = 8
            factors.append({"name": "Moderate treatment duration", "value": f"{duration} weeks", "impact": factor_score})
            base_score += factor_score
        
        # Invasive procedures
        if protocol.assessments.biopsies_required:
            factor_score = 15
            factors.append({"name": "Biopsies required", "value": protocol.assessments.biopsy_count, "impact": factor_score})
            base_score += factor_score
        
        # PK sampling burden
        if protocol.assessments.pk_sampling and protocol.assessments.pk_timepoints > 8:
            factor_score = 10
            factors.append({"name": "Intensive blood sampling", "value": protocol.assessments.pk_timepoints, "impact": factor_score})
            base_score += factor_score
        
        # PRO burden
        n_pro = len(protocol.assessments.patient_reported_outcomes)
        if n_pro > 5:
            factor_score = 10
            factors.append({"name": "Many PRO instruments", "value": n_pro, "impact": factor_score})
            base_score += factor_score
        
        # Telemedicine/home visits can reduce burden
        if protocol.visit_schedule.telemedicine_allowed or protocol.visit_schedule.home_visits_allowed:
            factor_score = -10
            factors.append({"name": "Flexible visit options", "value": True, "impact": factor_score})
            base_score += factor_score
        
        base_score = max(0, min(100, base_score))
        
        recommendations = []
        if total_visits > 15:
            recommendations.append("Consider patient travel reimbursement program")
            recommendations.append("Evaluate telemedicine options for non-critical visits")
        if protocol.assessments.biopsies_required:
            recommendations.append("Ensure clear patient communication about biopsy procedures")
        if base_score > 60:
            recommendations.append("Implement patient retention program with regular engagement")
        
        return ScoreBreakdown(
            score=round(base_score, 1),
            factors=factors,
            recommendations=recommendations
        )
    
    def _estimate_enrollment_rate(self, protocol: ParsedProtocol, enrollment_difficulty: float) -> float:
        """
        Estimate patients per site per month based on complexity
        Industry average is ~0.5-2 patients/site/month
        """
        # Base rate depends on phase
        phase = protocol.metadata.phase.lower() if protocol.metadata.phase else ""
        if "1" in phase:
            base_rate = 0.8
        elif "2" in phase:
            base_rate = 1.2
        elif "3" in phase:
            base_rate = 1.5
        else:
            base_rate = 1.0
        
        # Adjust for enrollment difficulty
        difficulty_factor = 1 - (enrollment_difficulty / 200)  # 0.5 to 1.0
        
        # Therapeutic area adjustment
        ta_mult = self._get_ta_multiplier(protocol.metadata.therapeutic_area)
        ta_factor = 1 / ta_mult  # Harder TAs = lower rate
        
        estimated_rate = base_rate * difficulty_factor * ta_factor
        return round(max(0.1, min(3.0, estimated_rate)), 2)
    
    def _estimate_screen_fail_rate(self, protocol: ParsedProtocol, enrollment_difficulty: float) -> float:
        """
        Estimate screen failure rate based on eligibility complexity
        Industry average is 20-40%
        """
        # Base rate
        base_rate = 25
        
        # Adjust for number of criteria
        n_criteria = len(protocol.eligibility.inclusion_criteria) + len(protocol.eligibility.exclusion_criteria)
        criteria_factor = min(20, n_criteria * 0.8)
        
        # Biomarker requirement significantly increases screen fail
        if protocol.eligibility.requires_biomarker:
            criteria_factor += 15
        
        # Therapeutic area adjustment
        ta = protocol.metadata.therapeutic_area.lower() if protocol.metadata.therapeutic_area else ""
        if "oncology" in ta:
            criteria_factor += 10
        elif "rare" in ta:
            criteria_factor += 20
        
        estimated_rate = base_rate + criteria_factor
        return round(min(80, max(10, estimated_rate)), 1)
    
    def _generate_site_profile(self, protocol: ParsedProtocol, scores: Dict[str, float]) -> Dict[str, Any]:
        """
        Generate recommended site profile based on protocol requirements
        """
        profile = {
            "minimum_experience_years": 3,
            "required_capabilities": [],
            "preferred_capabilities": [],
            "staff_requirements": [],
            "infrastructure_requirements": []
        }
        
        # Adjust experience based on complexity
        avg_complexity = sum(scores.values()) / len(scores)
        if avg_complexity > 70:
            profile["minimum_experience_years"] = 7
        elif avg_complexity > 50:
            profile["minimum_experience_years"] = 5
        
        # Required capabilities based on assessments
        if protocol.assessments.imaging_studies:
            profile["required_capabilities"].extend(protocol.assessments.imaging_studies)
        
        if protocol.assessments.biopsies_required:
            profile["required_capabilities"].append("Biopsy capability")
        
        if protocol.assessments.pk_sampling:
            profile["required_capabilities"].append("PK sample processing")
        
        if protocol.assessments.special_equipment:
            profile["required_capabilities"].extend(protocol.assessments.special_equipment)
        
        # Therapeutic area specific
        ta = protocol.metadata.therapeutic_area.lower() if protocol.metadata.therapeutic_area else ""
        if "oncology" in ta:
            profile["required_capabilities"].append("Oncology treatment capability")
            profile["staff_requirements"].append("Oncology-trained nursing staff")
        
        # Phase specific
        phase = protocol.metadata.phase.lower() if protocol.metadata.phase else ""
        if "1" in phase:
            profile["required_capabilities"].append("Phase 1 unit or equivalent")
            profile["staff_requirements"].append("24/7 medical coverage capability")
        
        # Staff requirements based on burden
        if scores.get("site_burden", 0) > 60:
            profile["staff_requirements"].append("Dedicated research coordinator")
            profile["staff_requirements"].append("Sub-investigator availability")
        
        return profile
    
    def _generate_pi_profile(self, protocol: ParsedProtocol, scores: Dict[str, float]) -> Dict[str, Any]:
        """
        Generate recommended PI profile based on protocol requirements
        """
        profile = {
            "minimum_publications": 5,
            "minimum_trials_experience": 3,
            "required_specialties": [],
            "preferred_experience": [],
            "board_certifications": []
        }
        
        # Adjust based on complexity
        avg_complexity = sum(scores.values()) / len(scores)
        if avg_complexity > 70:
            profile["minimum_publications"] = 15
            profile["minimum_trials_experience"] = 10
        elif avg_complexity > 50:
            profile["minimum_publications"] = 10
            profile["minimum_trials_experience"] = 5
        
        # Therapeutic area
        ta = protocol.metadata.therapeutic_area.lower() if protocol.metadata.therapeutic_area else ""
        if "oncology" in ta:
            profile["required_specialties"].append("Medical Oncology")
            profile["board_certifications"].append("Medical Oncology")
        elif "cardiology" in ta:
            profile["required_specialties"].append("Cardiology")
            profile["board_certifications"].append("Cardiovascular Disease")
        elif "neurology" in ta:
            profile["required_specialties"].append("Neurology")
            profile["board_certifications"].append("Neurology")
        
        # Phase specific
        phase = protocol.metadata.phase.lower() if protocol.metadata.phase else ""
        if "1" in phase:
            profile["preferred_experience"].append("Phase 1 trial experience")
            profile["preferred_experience"].append("Dose escalation study experience")
        
        # Indication specific
        indication = protocol.metadata.indication.lower() if protocol.metadata.indication else ""
        if indication:
            profile["preferred_experience"].append(f"Experience with {protocol.metadata.indication}")
        
        return profile
    
    def score_protocol(self, protocol: ParsedProtocol) -> ProtocolScores:
        """
        Generate complete scoring for a parsed protocol
        """
        # Calculate individual scores
        enrollment_difficulty = self._score_enrollment_difficulty(protocol)
        site_burden = self._score_site_burden(protocol)
        operational_complexity = self._score_operational_complexity(protocol)
        amendment_risk = self._score_amendment_risk(protocol)
        monitoring_complexity = self._score_monitoring_complexity(protocol)
        patient_burden = self._score_patient_burden(protocol)
        
        # Calculate overall complexity (weighted average)
        weights = {
            "enrollment": 0.20,
            "site_burden": 0.20,
            "operational": 0.25,
            "amendment": 0.10,
            "monitoring": 0.15,
            "patient": 0.10
        }
        
        overall = (
            enrollment_difficulty.score * weights["enrollment"] +
            site_burden.score * weights["site_burden"] +
            operational_complexity.score * weights["operational"] +
            amendment_risk.score * weights["amendment"] +
            monitoring_complexity.score * weights["monitoring"] +
            patient_burden.score * weights["patient"]
        )
        
        # Collect scores for profile generation
        score_dict = {
            "enrollment_difficulty": enrollment_difficulty.score,
            "site_burden": site_burden.score,
            "operational_complexity": operational_complexity.score,
            "amendment_risk": amendment_risk.score,
            "monitoring_complexity": monitoring_complexity.score,
            "patient_burden": patient_burden.score
        }
        
        return ProtocolScores(
            overall_complexity=round(overall, 1),
            enrollment_difficulty=enrollment_difficulty,
            site_burden=site_burden,
            operational_complexity=operational_complexity,
            amendment_risk=amendment_risk,
            monitoring_complexity=monitoring_complexity,
            patient_burden=patient_burden,
            estimated_enrollment_rate=self._estimate_enrollment_rate(protocol, enrollment_difficulty.score),
            estimated_screen_fail_rate=self._estimate_screen_fail_rate(protocol, enrollment_difficulty.score),
            recommended_site_profile=self._generate_site_profile(protocol, score_dict),
            recommended_pi_profile=self._generate_pi_profile(protocol, score_dict)
        )
