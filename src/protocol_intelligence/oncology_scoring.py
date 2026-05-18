"""
Oncology Protocol Scoring Engine
Computes oncology-specific operational scores and risk flags
"""

from typing import Dict, Any, List
from dataclasses import dataclass, asdict, field
from .oncology_parser import ParsedOncologyProtocol


@dataclass
class RiskFlag:
    """Individual risk flag with severity and details"""
    flag_name: str
    severity: str  # high, medium, low
    description: str
    mitigation: str = ""


@dataclass
class ScoreBreakdown:
    """Score with contributing factors"""
    score: float  # 0-100
    factors: List[Dict[str, Any]] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    @property
    def interpretation(self) -> str:
        """Human-readable interpretation of the score"""
        if self.score <= 25:
            return "Low"
        elif self.score <= 45:
            return "Moderate"
        elif self.score <= 65:
            return "High"
        else:
            return "Very High"
    
    @property
    def interpretation_detail(self) -> str:
        """Detailed explanation of what the score means"""
        if self.score <= 25:
            return "This area poses minimal challenges for trial execution"
        elif self.score <= 45:
            return "Some challenges expected; standard mitigation strategies should suffice"
        elif self.score <= 65:
            return "Significant challenges; proactive planning and experienced sites recommended"
        else:
            return "Major challenges; consider protocol optimization before launch"
    
    def to_dict(self) -> Dict[str, Any]:
        result = asdict(self)
        result["interpretation"] = self.interpretation
        result["interpretation_detail"] = self.interpretation_detail
        return result


@dataclass
class OncologyProtocolScores:
    """Complete oncology protocol scoring output"""
    # Core scores (0-100, higher = more difficult/complex)
    overall_complexity: float = 0.0
    enrollment_difficulty: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    site_burden: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    protocol_complexity: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    monitoring_complexity: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    amendment_risk: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    patient_burden: ScoreBreakdown = field(default_factory=ScoreBreakdown)
    
    # Oncology-specific risk flags
    risk_flags: List[RiskFlag] = field(default_factory=list)
    
    # Enrollment predictions
    estimated_screen_fail_rate: float = 0.0
    estimated_enrollment_rate: float = 0.0  # pts/site/month
    
    # Top bottlenecks
    top_enrollment_bottlenecks: List[str] = field(default_factory=list)
    
    # Site requirements
    site_capability_requirements: List[str] = field(default_factory=list)
    
    # Feasibility questions
    feasibility_questions: List[str] = field(default_factory=list)
    
    # Site matching criteria
    site_matching_criteria: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_complexity": self.overall_complexity,
            "enrollment_difficulty": self.enrollment_difficulty.to_dict(),
            "site_burden": self.site_burden.to_dict(),
            "protocol_complexity": self.protocol_complexity.to_dict(),
            "monitoring_complexity": self.monitoring_complexity.to_dict(),
            "amendment_risk": self.amendment_risk.to_dict(),
            "patient_burden": self.patient_burden.to_dict(),
            "risk_flags": [asdict(rf) for rf in self.risk_flags],
            "estimated_screen_fail_rate": self.estimated_screen_fail_rate,
            "estimated_enrollment_rate": self.estimated_enrollment_rate,
            "top_enrollment_bottlenecks": self.top_enrollment_bottlenecks,
            "site_capability_requirements": self.site_capability_requirements,
            "feasibility_questions": self.feasibility_questions,
            "site_matching_criteria": self.site_matching_criteria
        }


class OncologyProtocolScorer:
    """
    Scores oncology protocols for operational feasibility
    """
    
    # Biomarker prevalence estimates (approximate)
    BIOMARKER_PREVALENCE = {
        "HER2": 0.20,  # 20% of breast cancer
        "EGFR": 0.15,  # 15% of NSCLC
        "ALK": 0.05,  # 5% of NSCLC
        "ROS1": 0.02,  # 2% of NSCLC
        "BRAF": 0.08,  # 8% of melanoma, lower in others
        "KRAS": 0.45,  # ~45% of CRC have KRAS mutations (any type)
        "KRAS_G12C": 0.13,  # 13% of NSCLC specifically
        "KRAS_WILD": 0.55,  # ~55% are KRAS wild-type
        "MSI": 0.05,  # 5% across solid tumors (MSI-H)
        "PD_L1": 0.30,  # varies widely
        "BRCA": 0.15,  # 15% of ovarian, lower in others
        "NTRK": 0.01,  # <1% across tumors
        "RET": 0.02,
        "MET": 0.03,
        "FGFR": 0.05,
        "PIK3CA": 0.30,  # ~30% of breast cancer
        "TP53": 0.50,  # very common
        "ERBB2": 0.20,  # same as HER2
    }
    
    # Cancer type enrollment difficulty multipliers
    CANCER_DIFFICULTY = {
        "lung": 1.0,
        "breast": 0.9,
        "colorectal": 1.0,
        "melanoma": 1.1,
        "ovarian": 1.2,
        "prostate": 0.95,
        "pancreatic": 1.4,
        "gastric": 1.2,
        "hepatocellular": 1.3,
        "renal": 1.1,
        "bladder": 1.1,
        "head_and_neck": 1.2,
        "lymphoma": 1.1,
        "leukemia": 1.2,
        "myeloma": 1.15,
        "glioblastoma": 1.5,
        "sarcoma": 1.4,
        "default": 1.0
    }
    
    def __init__(self):
        pass
    
    def _get_cancer_multiplier(self, cancer_type: str) -> float:
        """Get enrollment difficulty multiplier for cancer type"""
        ct = cancer_type.lower() if cancer_type else ""
        for key, value in self.CANCER_DIFFICULTY.items():
            if key in ct:
                return value
        return self.CANCER_DIFFICULTY["default"]
    
    def _estimate_biomarker_prevalence(self, biomarkers: List[str]) -> float:
        """Estimate combined biomarker prevalence"""
        if not biomarkers:
            return 1.0  # No biomarker = 100% of patients eligible
        
        # For multiple biomarkers, multiply prevalences (assuming independence)
        combined = 1.0
        for bm in biomarkers:
            # Normalize the biomarker string
            bm_upper = bm.upper().replace("-", "_").replace(" ", "_")
            
            # Try to find a matching biomarker in our lookup table
            matched = False
            for key, prev in self.BIOMARKER_PREVALENCE.items():
                key_upper = key.upper()
                # Check if key is contained in biomarker string or vice versa
                if key_upper in bm_upper or bm_upper in key_upper:
                    combined *= prev
                    matched = True
                    break
            
            if not matched:
                # Unknown biomarker, assume 10% prevalence
                combined *= 0.10
        
        return combined
    
    def _safe_int(self, val, default=0) -> int:
        """Safely convert to int, handling None"""
        if val is None:
            return default
        try:
            return int(val)
        except (TypeError, ValueError):
            return default
    
    def _safe_str(self, val, default="") -> str:
        """Safely convert to string, handling None"""
        return str(val).lower() if val else default
    
    def _infer_line_of_therapy(self, protocol: ParsedOncologyProtocol) -> str:
        """Infer line of therapy from prior therapy requirements if not explicitly stated"""
        lot = self._safe_str(protocol.population.line_of_therapy)
        
        # If LLM gave a specific line, use it
        if lot and lot not in ["any", "unknown", ""]:
            return lot
        
        # Infer from prior therapy requirements
        prior_therapy = protocol.population.prior_therapy_required or []
        n_prior = len(prior_therapy)
        
        # Check for standard CRC treatments (fluoropyrimidine, irinotecan, oxaliplatin)
        prior_lower = [p.lower() for p in prior_therapy]
        prior_text = " ".join(prior_lower)
        
        # Common 1L/2L drugs that indicate late-line if all required
        standard_crc = ["fluoropyrimidine", "irinotecan", "oxaliplatin"]
        standard_nsclc = ["platinum", "immunotherapy", "chemotherapy"]
        
        crc_count = sum(1 for drug in standard_crc if any(drug in p for p in prior_lower))
        
        if crc_count >= 3 or n_prior >= 3:
            return "3l_plus_inferred"
        elif n_prior >= 2 or crc_count >= 2:
            return "2l_inferred"
        elif n_prior >= 1:
            return "2l_inferred"
        
        return lot
    
    def _score_enrollment_difficulty(self, protocol: ParsedOncologyProtocol) -> ScoreBreakdown:
        """Score enrollment difficulty based on oncology-specific factors"""
        factors = []
        base_score = 25
        
        # Line of therapy (with inference from prior therapy)
        lot = self._infer_line_of_therapy(protocol)
        if "3l" in lot or "3+" in lot or "third" in lot:
            inferred = "_inferred" in lot
            factors.append({"name": "Late-line therapy (3L+)", "value": f"{lot}{' (inferred from prior therapy)' if inferred else ''}", "impact": 20})
            base_score += 20
        elif "2l" in lot or "second" in lot:
            inferred = "_inferred" in lot
            factors.append({"name": "Second-line therapy", "value": f"{lot}{' (inferred)' if inferred else ''}", "impact": 10})
            base_score += 10
        elif "1l" in lot or "first" in lot:
            factors.append({"name": "First-line therapy", "value": lot, "impact": 5})
            base_score += 5
        
        # Biomarker requirements
        biomarkers = protocol.population.biomarker_requirements
        if biomarkers:
            prevalence = self._estimate_biomarker_prevalence(biomarkers)
            if prevalence < 0.05:
                factors.append({"name": "Rare biomarker (<5%)", "value": biomarkers, "impact": 25})
                base_score += 25
            elif prevalence < 0.15:
                factors.append({"name": "Uncommon biomarker (5-15%)", "value": biomarkers, "impact": 15})
                base_score += 15
            elif prevalence < 0.30:
                factors.append({"name": "Moderate biomarker (15-30%)", "value": biomarkers, "impact": 8})
                base_score += 8
        
        # Prior therapy requirements
        prior_therapy = protocol.population.prior_therapy_required or []
        if prior_therapy:
            n_prior = len(prior_therapy)
            if n_prior >= 3:
                factors.append({"name": "Multiple prior therapies required", "value": n_prior, "impact": 15})
                base_score += 15
            elif n_prior >= 1:
                factors.append({"name": "Specific prior therapy required", "value": n_prior, "impact": 8})
                base_score += 8
        
        # Exclusion criteria count
        n_exclusions = len(protocol.population.exclusion_criteria or [])
        if n_exclusions > 20:
            factors.append({"name": "Many exclusion criteria", "value": n_exclusions, "impact": 15})
            base_score += 15
        elif n_exclusions > 12:
            factors.append({"name": "Moderate exclusion criteria", "value": n_exclusions, "impact": 8})
            base_score += 8
        
        # CNS metastases exclusion
        if not protocol.population.cns_metastases_allowed:
            factors.append({"name": "CNS metastases excluded", "value": True, "impact": 8})
            base_score += 8
        
        # ECOG restriction
        ecog = protocol.population.ecog_performance_status
        if ecog and "0-1" in ecog:
            factors.append({"name": "Strict ECOG (0-1 only)", "value": ecog, "impact": 5})
            base_score += 5
        
        # Cancer type multiplier
        cancer_mult = self._get_cancer_multiplier(protocol.indication.cancer_type)
        if cancer_mult > 1.2:
            factors.append({"name": "Difficult cancer type", "value": protocol.indication.cancer_type, "impact": 10})
            base_score += 10
        
        base_score = min(100, base_score * cancer_mult)
        
        # Recommendations
        recommendations = []
        if biomarkers and self._estimate_biomarker_prevalence(biomarkers) < 0.10:
            recommendations.append("Consider central biomarker testing to maximize screening efficiency")
            recommendations.append("Partner with sites that have high-volume molecular testing programs")
        if "3l" in lot or "3+" in lot:
            recommendations.append("Focus on academic centers with large referral populations")
        if not protocol.population.cns_metastases_allowed:
            recommendations.append("Consider allowing stable/treated CNS metastases to broaden eligibility")
        if n_exclusions > 15:
            recommendations.append("Review exclusion criteria for potential relaxation per ASCO guidelines")
        
        return ScoreBreakdown(
            score=round(base_score, 1),
            factors=factors,
            recommendations=recommendations
        )
    
    def _score_site_burden(self, protocol: ParsedOncologyProtocol) -> ScoreBreakdown:
        """Score operational burden on sites"""
        factors = []
        base_score = 20
        
        # Biopsy requirements
        total_biopsies = self._safe_int(protocol.operational.total_biopsies)
        if protocol.operational.on_treatment_biopsy_required:
            factors.append({"name": "On-treatment biopsy required", "value": True, "impact": 15})
            base_score += 15
        if protocol.operational.screening_biopsy_required:
            factors.append({"name": "Screening biopsy required", "value": True, "impact": 10})
            base_score += 10
        if total_biopsies >= 3:
            factors.append({"name": "Multiple biopsies", "value": total_biopsies, "impact": 10})
            base_score += 10
        
        # Imaging burden
        imaging_freq = protocol.endpoints.imaging_frequency.lower() if protocol.endpoints.imaging_frequency else ""
        if "q6w" in imaging_freq or "6 week" in imaging_freq:
            factors.append({"name": "Frequent imaging (q6w)", "value": imaging_freq, "impact": 12})
            base_score += 12
        elif "q8w" in imaging_freq or "8 week" in imaging_freq:
            factors.append({"name": "Standard imaging (q8w)", "value": imaging_freq, "impact": 6})
            base_score += 6
        
        # Central requirements
        if protocol.operational.central_imaging_required:
            factors.append({"name": "Central imaging review", "value": True, "impact": 8})
            base_score += 8
        if protocol.operational.central_lab_required:
            factors.append({"name": "Central lab required", "value": True, "impact": 5})
            base_score += 5
        
        # PK sampling
        if protocol.operational.pk_sampling_required:
            pk_points = self._safe_int(protocol.operational.pk_timepoints_per_cycle)
            if pk_points > 6:
                factors.append({"name": "Intensive PK sampling", "value": pk_points, "impact": 15})
                base_score += 15
            else:
                factors.append({"name": "PK sampling required", "value": pk_points, "impact": 8})
                base_score += 8
        
        # Cardiac monitoring
        if protocol.operational.echo_muga_required:
            factors.append({"name": "ECHO/MUGA required", "value": True, "impact": 8})
            base_score += 8
        
        # Visit frequency
        visits_per_cycle = self._safe_int(protocol.operational.treatment_visits_per_cycle)
        if visits_per_cycle >= 3:
            factors.append({"name": "Frequent visits per cycle", "value": visits_per_cycle, "impact": 10})
            base_score += 10
        
        base_score = min(100, base_score)
        
        recommendations = []
        if protocol.operational.on_treatment_biopsy_required:
            recommendations.append("Ensure sites have interventional radiology support")
        if protocol.operational.central_imaging_required:
            recommendations.append("Set up central imaging vendor early to avoid delays")
        if protocol.operational.pk_sampling_required and self._safe_int(protocol.operational.pk_timepoints_per_cycle) > 6:
            recommendations.append("Consider sparse PK sampling to reduce patient/site burden")
        
        return ScoreBreakdown(
            score=round(base_score, 1),
            factors=factors,
            recommendations=recommendations
        )
    
    def _score_protocol_complexity(self, protocol: ParsedOncologyProtocol) -> ScoreBreakdown:
        """Score overall protocol complexity"""
        factors = []
        base_score = 20
        
        # Phase
        phase = protocol.metadata.phase.lower() if protocol.metadata.phase else ""
        if "1" in phase and "2" not in phase:
            factors.append({"name": "Phase 1 study", "value": phase, "impact": 15})
            base_score += 15
        elif "1/2" in phase or "1b/2" in phase:
            factors.append({"name": "Phase 1/2 study", "value": phase, "impact": 12})
            base_score += 12
        
        # Design type
        design = protocol.design.design_type.lower() if protocol.design.design_type else ""
        if "basket" in design or "umbrella" in design or "platform" in design:
            factors.append({"name": "Complex trial design", "value": design, "impact": 15})
            base_score += 15
        if protocol.design.adaptive_design:
            factors.append({"name": "Adaptive design", "value": True, "impact": 12})
            base_score += 12
        if protocol.design.dose_escalation:
            factors.append({"name": "Dose escalation", "value": True, "impact": 10})
            base_score += 10
        
        # Number of arms
        n_arms = self._safe_int(protocol.design.number_of_arms, 1)
        if n_arms > 3:
            factors.append({"name": "Multiple treatment arms", "value": n_arms, "impact": 12})
            base_score += 12
        elif n_arms > 1:
            factors.append({"name": "Multi-arm study", "value": n_arms, "impact": 5})
            base_score += 5
        
        # Expansion cohorts
        if protocol.design.expansion_cohorts:
            n_cohorts = len(protocol.design.expansion_cohorts)
            factors.append({"name": "Expansion cohorts", "value": n_cohorts, "impact": 8})
            base_score += 8
        
        # Combination therapy
        if protocol.intervention.combination_agents:
            factors.append({"name": "Combination therapy", "value": len(protocol.intervention.combination_agents), "impact": 8})
            base_score += 8
        
        base_score = min(100, base_score)
        
        recommendations = []
        if protocol.design.dose_escalation:
            recommendations.append("Ensure 24/7 medical coverage for DLT assessment")
        if protocol.design.adaptive_design:
            recommendations.append("Engage biostatistics early for adaptive design implementation")
        if "basket" in design or "umbrella" in design:
            recommendations.append("Consider tumor-agnostic site selection strategy")
        
        return ScoreBreakdown(
            score=round(base_score, 1),
            factors=factors,
            recommendations=recommendations
        )
    
    def _score_monitoring_complexity(self, protocol: ParsedOncologyProtocol) -> ScoreBreakdown:
        """Score safety monitoring complexity"""
        factors = []
        base_score = 20
        
        # DSMB
        if protocol.safety.dsmb_required:
            factors.append({"name": "DSMB required", "value": True, "impact": 10})
            base_score += 10
        
        # Interim analyses
        if protocol.safety.interim_analyses > 1:
            factors.append({"name": "Multiple interim analyses", "value": protocol.safety.interim_analyses, "impact": 10})
            base_score += 10
        
        # Organ monitoring
        organ_monitors = sum([
            protocol.safety.cardiac_monitoring,
            protocol.safety.hepatotoxicity_monitoring,
            protocol.safety.nephrotoxicity_monitoring,
            protocol.safety.neurotoxicity_monitoring,
            protocol.safety.pulmonary_monitoring
        ])
        if organ_monitors >= 3:
            factors.append({"name": "Multiple organ monitoring", "value": organ_monitors, "impact": 15})
            base_score += 15
        elif organ_monitors > 0:
            factors.append({"name": "Organ-specific monitoring", "value": organ_monitors, "impact": 8})
            base_score += 8
        
        # Immunotherapy-specific
        if protocol.safety.irae_monitoring:
            factors.append({"name": "irAE monitoring (immunotherapy)", "value": True, "impact": 10})
            base_score += 10
        if protocol.safety.cytokine_release_monitoring:
            factors.append({"name": "CRS monitoring (cell therapy)", "value": True, "impact": 15})
            base_score += 15
        
        # Dose escalation
        if protocol.safety.dose_escalation_scheme:
            factors.append({"name": "Dose escalation scheme", "value": protocol.safety.dose_escalation_scheme, "impact": 8})
            base_score += 8
        
        base_score = min(100, base_score)
        
        recommendations = []
        if protocol.safety.irae_monitoring:
            recommendations.append("Ensure sites have irAE management protocols in place")
        if protocol.safety.cytokine_release_monitoring:
            recommendations.append("Require ICU access for CRS management")
        if protocol.safety.cardiac_monitoring:
            recommendations.append("Establish cardiac safety monitoring committee")
        
        return ScoreBreakdown(
            score=round(base_score, 1),
            factors=factors,
            recommendations=recommendations
        )
    
    def _score_amendment_risk(self, protocol: ParsedOncologyProtocol) -> ScoreBreakdown:
        """Predict amendment risk"""
        factors = []
        base_score = 20
        
        # Phase 1 = higher amendment risk
        phase = protocol.metadata.phase.lower() if protocol.metadata.phase else ""
        if "1" in phase:
            factors.append({"name": "Early phase study", "value": phase, "impact": 15})
            base_score += 15
        
        # Dose escalation
        if protocol.design.dose_escalation:
            factors.append({"name": "Dose escalation design", "value": True, "impact": 12})
            base_score += 12
        
        # Complex eligibility
        n_criteria = len(protocol.population.inclusion_criteria or []) + len(protocol.population.exclusion_criteria or [])
        if n_criteria > 30:
            factors.append({"name": "Complex eligibility", "value": n_criteria, "impact": 15})
            base_score += 15
        elif n_criteria > 20:
            factors.append({"name": "Moderate eligibility complexity", "value": n_criteria, "impact": 8})
            base_score += 8
        
        # Multiple biomarkers
        biomarkers = protocol.population.biomarker_requirements or []
        if len(biomarkers) > 2:
            factors.append({"name": "Multiple biomarker requirements", "value": len(protocol.population.biomarker_requirements), "impact": 10})
            base_score += 10
        
        # Novel endpoints
        endpoint = protocol.endpoints.primary_endpoint.lower() if protocol.endpoints.primary_endpoint else ""
        if "pk" in endpoint or "pd" in endpoint or "biomarker" in endpoint:
            factors.append({"name": "Novel/exploratory endpoint", "value": endpoint, "impact": 8})
            base_score += 8
        
        base_score = min(100, base_score)
        
        recommendations = []
        if base_score > 60:
            recommendations.append("Build amendment flexibility into site contracts")
            recommendations.append("Consider protocol optimization review before finalization")
        if protocol.design.dose_escalation:
            recommendations.append("Pre-define dose modification rules to minimize amendments")
        
        return ScoreBreakdown(
            score=round(base_score, 1),
            factors=factors,
            recommendations=recommendations
        )
    
    def _score_patient_burden(self, protocol: ParsedOncologyProtocol) -> ScoreBreakdown:
        """Score burden on patients"""
        factors = []
        base_score = 20
        
        # Biopsies
        if protocol.operational.on_treatment_biopsy_required:
            factors.append({"name": "On-treatment biopsy", "value": True, "impact": 15})
            base_score += 15
        if self._safe_int(protocol.operational.total_biopsies) >= 2:
            factors.append({"name": "Multiple biopsies", "value": protocol.operational.total_biopsies, "impact": 10})
            base_score += 10
        
        # Visit frequency
        visits = self._safe_int(protocol.operational.treatment_visits_per_cycle)
        cycle_days = self._safe_int(protocol.operational.cycle_length_days, 21)
        if visits >= 2 and cycle_days <= 21:
            factors.append({"name": "Frequent visits", "value": f"{visits} per {cycle_days}d cycle", "impact": 12})
            base_score += 12
        
        # PK sampling
        pk_points = self._safe_int(protocol.operational.pk_timepoints_per_cycle)
        if protocol.operational.pk_sampling_required and pk_points > 6:
            factors.append({"name": "Intensive blood draws", "value": pk_points, "impact": 10})
            base_score += 10
        
        # Hospitalization
        if protocol.operational.hospitalization_required:
            factors.append({"name": "Hospitalization required", "value": True, "impact": 15})
            base_score += 15
        
        # Imaging frequency
        imaging_freq = protocol.endpoints.imaging_frequency.lower() if protocol.endpoints.imaging_frequency else ""
        if "q6w" in imaging_freq:
            factors.append({"name": "Frequent imaging", "value": imaging_freq, "impact": 8})
            base_score += 8
        
        base_score = min(100, base_score)
        
        recommendations = []
        if base_score > 50:
            recommendations.append("Implement patient travel reimbursement program")
            recommendations.append("Consider patient concierge services for complex visits")
        if protocol.operational.on_treatment_biopsy_required:
            recommendations.append("Provide clear patient education on biopsy procedures")
        
        return ScoreBreakdown(
            score=round(base_score, 1),
            factors=factors,
            recommendations=recommendations
        )
    
    def _identify_risk_flags(self, protocol: ParsedOncologyProtocol) -> List[RiskFlag]:
        """Identify oncology-specific risk flags"""
        flags = []
        
        # Rare biomarker
        biomarkers = protocol.population.biomarker_requirements or []
        if biomarkers:
            prevalence = self._estimate_biomarker_prevalence(biomarkers)
            if prevalence < 0.05:
                flags.append(RiskFlag(
                    flag_name="Rare Biomarker Requirement",
                    severity="high",
                    description=f"Biomarker(s) {biomarkers} have <5% prevalence, severely limiting patient pool",
                    mitigation="Partner with molecular testing labs, consider basket design"
                ))
            elif prevalence < 0.15:
                flags.append(RiskFlag(
                    flag_name="Uncommon Biomarker",
                    severity="medium",
                    description=f"Biomarker(s) {biomarkers} have 5-15% prevalence",
                    mitigation="Ensure robust screening program with central testing"
                ))
        
        # Late-line therapy (use inference logic)
        lot = self._infer_line_of_therapy(protocol)
        if "3l" in lot or "3+" in lot or "heavily pretreated" in lot:
            inferred = "_inferred" in lot
            flags.append(RiskFlag(
                flag_name="Late-Line of Therapy",
                severity="high",
                description=f"3L+ patients are difficult to find and often have poor performance status{' (inferred from prior therapy requirements)' if inferred else ''}",
                mitigation="Focus on high-volume academic centers with large referral networks"
            ))
        
        # Mandatory biopsies
        if protocol.operational.on_treatment_biopsy_required:
            flags.append(RiskFlag(
                flag_name="Mandatory On-Treatment Biopsy",
                severity="medium",
                description="On-treatment biopsies increase patient burden and screen failures",
                mitigation="Consider making biopsies optional or limiting to accessible lesions"
            ))
        
        # CNS exclusion in brain-metastatic cancers
        if not protocol.population.cns_metastases_allowed:
            cancer = protocol.indication.cancer_type.lower() if protocol.indication.cancer_type else ""
            if cancer in ["lung", "breast", "melanoma"]:
                flags.append(RiskFlag(
                    flag_name="CNS Metastases Excluded",
                    severity="medium",
                    description=f"CNS mets common in {cancer} cancer; exclusion limits enrollment",
                    mitigation="Consider allowing stable/treated CNS metastases"
                ))
        
        # Strict ECOG
        ecog = protocol.population.ecog_performance_status or ""
        is_strict_ecog = "0-1" in ecog and "2" not in ecog
        
        # Check for contradiction: 3L+ with strict ECOG is problematic
        if is_strict_ecog and ("3l" in lot or "3+" in lot):
            flags.append(RiskFlag(
                flag_name="ECOG/Line-of-Therapy Mismatch",
                severity="high",
                description="3L+ patients often have ECOG 2 due to disease progression and prior treatment toxicity; requiring ECOG 0-1 severely limits the eligible population",
                mitigation="Consider allowing ECOG 0-2, or at minimum ECOG 2 with investigator discretion"
            ))
        elif is_strict_ecog:
            flags.append(RiskFlag(
                flag_name="Strict Performance Status",
                severity="low",
                description="ECOG 0-1 only excludes many real-world patients",
                mitigation="Consider expanding to ECOG 0-2 for expansion cohorts"
            ))
        
        # Heavy imaging burden
        imaging_freq = protocol.endpoints.imaging_frequency.lower() if protocol.endpoints.imaging_frequency else ""
        if "q6w" in imaging_freq:
            flags.append(RiskFlag(
                flag_name="Frequent Imaging Schedule",
                severity="low",
                description="Q6W imaging increases site burden and costs",
                mitigation="Consider q8w after initial response assessment"
            ))
        
        # Cell therapy complexity
        intervention = protocol.intervention.intervention_type.lower() if protocol.intervention.intervention_type else ""
        if "cell_therapy" in intervention or "car" in intervention:
            flags.append(RiskFlag(
                flag_name="Cell Therapy Complexity",
                severity="high",
                description="Cell therapy requires specialized manufacturing and administration",
                mitigation="Limit to certified cell therapy centers with ICU access"
            ))
        
        # Phase 1 with expansion
        if protocol.design.dose_escalation and protocol.design.expansion_cohorts:
            flags.append(RiskFlag(
                flag_name="Phase 1 with Multiple Expansions",
                severity="medium",
                description="Multiple expansion cohorts increase operational complexity",
                mitigation="Stagger cohort activation to manage site workload"
            ))
        
        return flags
    
    def _generate_enrollment_bottlenecks(self, protocol: ParsedOncologyProtocol, enrollment_score: float) -> List[str]:
        """Identify top enrollment bottlenecks"""
        bottlenecks = []
        
        # Biomarker
        biomarkers = protocol.population.biomarker_requirements or []
        if biomarkers:
            prevalence = self._estimate_biomarker_prevalence(biomarkers)
            if prevalence < 0.15:
                bottlenecks.append(f"Biomarker requirement ({', '.join(biomarkers)}) limits eligible population to ~{prevalence*100:.0f}%")
        
        # Line of therapy
        lot = protocol.population.line_of_therapy
        if lot and ("3" in lot or "heavily" in lot.lower()):
            bottlenecks.append(f"Late-line requirement ({lot}) significantly reduces available patients")
        
        # Prior therapy
        prior_therapy = protocol.population.prior_therapy_required or []
        if prior_therapy:
            bottlenecks.append(f"Specific prior therapy required: {', '.join(prior_therapy[:3])}")
        
        # CNS exclusion
        if not protocol.population.cns_metastases_allowed:
            bottlenecks.append("CNS metastases exclusion removes 20-40% of metastatic patients")
        
        # Biopsy requirement
        if protocol.operational.screening_biopsy_required:
            bottlenecks.append("Mandatory screening biopsy may cause 10-15% screen failures")
        
        # Performance status
        if protocol.population.ecog_performance_status == "0-1":
            bottlenecks.append("ECOG 0-1 requirement excludes patients with declining status")
        
        return bottlenecks[:5]  # Top 5
    
    def _generate_site_requirements(self, protocol: ParsedOncologyProtocol) -> List[str]:
        """Generate site capability requirements"""
        requirements = []
        
        # Phase-specific
        phase = protocol.metadata.phase.lower() if protocol.metadata.phase else ""
        if "1" in phase:
            requirements.append("Phase 1 unit or equivalent with 24/7 coverage")
        
        # Biomarker testing
        if protocol.population.biomarker_requirements:
            method = protocol.population.biomarker_testing_method
            if method and "ngs" in method.lower():
                requirements.append("NGS testing capability or central lab partnership")
            else:
                requirements.append("Molecular pathology for biomarker testing")
        
        # Biopsy
        if protocol.operational.on_treatment_biopsy_required or protocol.operational.screening_biopsy_required:
            requirements.append("Interventional radiology for tumor biopsies")
        
        # Imaging
        if protocol.endpoints.imaging_modality:
            modalities = protocol.endpoints.imaging_modality
            if "PET" in modalities:
                requirements.append("PET/CT imaging capability")
            if "MRI" in modalities:
                requirements.append("MRI with oncology protocols")
        
        # Cardiac
        if protocol.operational.echo_muga_required or protocol.safety.cardiac_monitoring:
            requirements.append("Cardiology support for cardiac monitoring")
        
        # Cell therapy
        intervention = protocol.intervention.intervention_type.lower() if protocol.intervention.intervention_type else ""
        if "cell_therapy" in intervention:
            requirements.append("Cell therapy certification (FACT accredited)")
            requirements.append("ICU access for CRS management")
        
        # Immunotherapy
        if protocol.safety.irae_monitoring:
            requirements.append("irAE management protocols and multidisciplinary support")
        
        # Central requirements
        if protocol.operational.central_imaging_required:
            requirements.append("Ability to submit images to central reader")
        
        return requirements
    
    def _generate_feasibility_questions(self, protocol: ParsedOncologyProtocol) -> List[str]:
        """Generate questions to ask sites during feasibility"""
        questions = []
        
        # Enrollment
        cancer = protocol.indication.cancer_type or "this indication"
        questions.append(f"How many new {cancer} patients do you see per month?")
        
        if protocol.population.biomarker_requirements:
            bm = ", ".join(protocol.population.biomarker_requirements[:2])
            questions.append(f"What is your current testing rate for {bm}?")
            questions.append("Do you have NGS testing in-house or use a reference lab?")
        
        lot = protocol.population.line_of_therapy
        if lot and ("2" in lot or "3" in lot):
            questions.append(f"How many {lot} patients do you treat annually?")
        
        # Operational
        if protocol.operational.on_treatment_biopsy_required:
            questions.append("Do you have IR support for research biopsies?")
            questions.append("What is your typical biopsy turnaround time?")
        
        if protocol.operational.pk_sampling_required:
            questions.append("Do you have research nursing support for intensive PK sampling?")
        
        # Phase 1
        phase = protocol.metadata.phase.lower() if protocol.metadata.phase else ""
        if "1" in phase:
            questions.append("Do you have a dedicated Phase 1 unit?")
            questions.append("What is your DLT reporting process?")
        
        # Competition
        questions.append("What competing trials are currently enrolling in this indication?")
        questions.append("What is your typical screen-to-enroll ratio for oncology trials?")
        
        return questions[:8]
    
    def _generate_site_matching_criteria(self, protocol: ParsedOncologyProtocol, scores: Dict[str, float]) -> Dict[str, Any]:
        """Generate criteria for site matching engine"""
        criteria = {
            "therapeutic_area": "oncology",
            "cancer_type": protocol.indication.cancer_type,
            "tumor_type": protocol.indication.tumor_type,
            "phase": protocol.metadata.phase,
            "minimum_experience": {
                "oncology_trials": 5,
                "phase_specific": 3
            },
            "required_capabilities": [],
            "preferred_capabilities": [],
            "volume_requirements": {},
            "complexity_tolerance": "high" if scores.get("overall", 0) > 60 else "medium"
        }
        
        # Add capabilities based on protocol
        if protocol.population.biomarker_requirements:
            criteria["required_capabilities"].append("molecular_testing")
        if protocol.operational.on_treatment_biopsy_required:
            criteria["required_capabilities"].append("interventional_radiology")
        if "1" in (protocol.metadata.phase or ""):
            criteria["required_capabilities"].append("phase_1_unit")
        if protocol.safety.irae_monitoring:
            criteria["required_capabilities"].append("immunotherapy_experience")
        
        # Volume requirements
        if protocol.design.target_enrollment > 0:
            sites_needed = max(10, protocol.design.target_enrollment // 5)
            criteria["volume_requirements"]["minimum_patients_per_site"] = 3
            criteria["volume_requirements"]["target_sites"] = sites_needed
        
        return criteria
    
    def score_protocol(self, protocol: ParsedOncologyProtocol) -> OncologyProtocolScores:
        """Generate complete scoring for an oncology protocol"""
        
        # Calculate individual scores
        enrollment = self._score_enrollment_difficulty(protocol)
        site_burden = self._score_site_burden(protocol)
        complexity = self._score_protocol_complexity(protocol)
        monitoring = self._score_monitoring_complexity(protocol)
        amendment = self._score_amendment_risk(protocol)
        patient = self._score_patient_burden(protocol)
        
        # Overall complexity (weighted)
        overall = (
            enrollment.score * 0.25 +
            site_burden.score * 0.20 +
            complexity.score * 0.20 +
            monitoring.score * 0.15 +
            amendment.score * 0.10 +
            patient.score * 0.10
        )
        
        # Risk flags
        risk_flags = self._identify_risk_flags(protocol)
        
        # Enrollment predictions
        base_rate = 0.8 if "1" in (protocol.metadata.phase or "") else 1.2
        enrollment_rate = base_rate * (1 - enrollment.score / 200)
        screen_fail = 25 + (enrollment.score * 0.5)
        
        # Generate outputs
        scores_dict = {"overall": overall, "enrollment": enrollment.score}
        
        return OncologyProtocolScores(
            overall_complexity=round(overall, 1),
            enrollment_difficulty=enrollment,
            site_burden=site_burden,
            protocol_complexity=complexity,
            monitoring_complexity=monitoring,
            amendment_risk=amendment,
            patient_burden=patient,
            risk_flags=risk_flags,
            estimated_screen_fail_rate=round(min(80, screen_fail), 1),
            estimated_enrollment_rate=round(max(0.1, enrollment_rate), 2),
            top_enrollment_bottlenecks=self._generate_enrollment_bottlenecks(protocol, enrollment.score),
            site_capability_requirements=self._generate_site_requirements(protocol),
            feasibility_questions=self._generate_feasibility_questions(protocol),
            site_matching_criteria=self._generate_site_matching_criteria(protocol, scores_dict)
        )
