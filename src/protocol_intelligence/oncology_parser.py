"""
Oncology Protocol Parser
Specialized parser for oncology clinical trial protocols
Extracts oncology-specific fields: endpoints, RECIST criteria, biomarkers, etc.
"""

import os
import json
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict, field
from openai import OpenAI

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


@dataclass
class OncologyProtocolMetadata:
    """Basic protocol identification"""
    trial_title: str = ""
    protocol_number: str = ""
    sponsor: str = ""
    phase: str = ""  # Phase 1, 1/2, 2, 2/3, 3, 4
    version: str = ""
    version_date: str = ""


@dataclass
class CancerIndication:
    """Cancer type and classification"""
    cancer_type: str = ""  # breast, lung, colorectal, melanoma, etc.
    cancer_subtype: str = ""  # NSCLC, SCLC, HER2+, triple-negative, etc.
    tumor_type: str = ""  # solid_tumor, hematologic, unknown
    histology: str = ""  # adenocarcinoma, squamous, etc.
    stage: str = ""  # metastatic, locally_advanced, early_stage


@dataclass
class Intervention:
    """Treatment intervention details"""
    intervention_type: str = ""  # small_molecule, antibody, immunotherapy, cell_therapy, ADC, combination
    drug_name: str = ""
    drug_class: str = ""  # TKI, checkpoint_inhibitor, CDK4/6, etc.
    mechanism_of_action: str = ""
    route_of_administration: str = ""  # oral, IV, SC
    dosing_schedule: str = ""
    combination_agents: List[str] = field(default_factory=list)


@dataclass 
class PatientPopulation:
    """Eligibility and patient population details"""
    line_of_therapy: str = ""  # 1L, 2L, 3L+, any, maintenance
    biomarker_requirements: List[str] = field(default_factory=list)  # HER2+, EGFR+, BRAF V600E, PD-L1>=1%, etc.
    biomarker_testing_method: str = ""  # IHC, FISH, NGS, PCR
    prior_therapy_required: List[str] = field(default_factory=list)
    prior_therapy_excluded: List[str] = field(default_factory=list)
    washout_periods: Dict[str, str] = field(default_factory=dict)  # {"chemotherapy": "4 weeks", "immunotherapy": "6 weeks"}
    ecog_performance_status: str = ""  # 0-1, 0-2
    measurable_disease_required: bool = True
    cns_metastases_allowed: bool = False
    cns_metastases_conditions: str = ""
    age_range: Dict[str, int] = field(default_factory=lambda: {"min": 18, "max": None})
    organ_function_requirements: List[str] = field(default_factory=list)
    inclusion_criteria: List[str] = field(default_factory=list)
    exclusion_criteria: List[str] = field(default_factory=list)


@dataclass
class EndpointsAndResponse:
    """Endpoints and response assessment"""
    primary_endpoint: str = ""  # OS, PFS, ORR, DLT/MTD, safety, PK
    primary_endpoint_definition: str = ""
    secondary_endpoints: List[str] = field(default_factory=list)
    exploratory_endpoints: List[str] = field(default_factory=list)
    response_criteria: str = ""  # RECIST_1.1, iRECIST, Lugano, RANO, mRECIST
    imaging_modality: List[str] = field(default_factory=list)  # CT, MRI, PET
    imaging_frequency: str = ""  # q6w, q8w, q12w
    tumor_assessment_schedule: str = ""
    survival_follow_up: str = ""


@dataclass
class OperationalBurden:
    """Site and patient operational requirements"""
    # Biopsies
    screening_biopsy_required: bool = False
    on_treatment_biopsy_required: bool = False
    progression_biopsy_required: bool = False
    biopsy_type: str = ""  # core needle, excisional, liquid
    total_biopsies: int = 0
    
    # Visits and assessments
    screening_period_days: int = 28
    treatment_visits_per_cycle: int = 1
    cycle_length_days: int = 21
    total_visits_estimate: int = 0
    visit_duration_hours: float = 0
    
    # Labs and monitoring
    lab_frequency: str = ""
    lab_tests: List[str] = field(default_factory=list)
    ecg_required: bool = False
    ecg_frequency: str = ""
    echo_muga_required: bool = False
    echo_muga_frequency: str = ""
    
    # PK/PD
    pk_sampling_required: bool = False
    pk_timepoints_per_cycle: int = 0
    pk_intensive_days: List[int] = field(default_factory=list)
    
    # Special requirements
    hospitalization_required: bool = False
    central_lab_required: bool = False
    central_imaging_required: bool = False


@dataclass
class SafetyMonitoring:
    """Safety monitoring requirements"""
    dlt_assessment_window: str = ""  # Phase 1
    dose_escalation_scheme: str = ""  # 3+3, BOIN, CRM
    dsmb_required: bool = False
    interim_analyses: int = 0
    
    # Organ-specific monitoring
    cardiac_monitoring: bool = False
    cardiac_monitoring_details: str = ""
    hepatotoxicity_monitoring: bool = False
    nephrotoxicity_monitoring: bool = False
    neurotoxicity_monitoring: bool = False
    pulmonary_monitoring: bool = False
    dermatologic_monitoring: bool = False
    
    # Immunotherapy-specific
    irae_monitoring: bool = False  # immune-related adverse events
    cytokine_release_monitoring: bool = False  # for cell therapy
    
    special_safety_concerns: List[str] = field(default_factory=list)


@dataclass
class TrialDesign:
    """Study design parameters"""
    design_type: str = ""  # single_arm, randomized, dose_escalation, basket, umbrella, platform
    randomization_ratio: str = ""
    stratification_factors: List[str] = field(default_factory=list)
    blinding: str = ""  # open_label, single_blind, double_blind
    control_arm: str = ""  # none, placebo, active_comparator, SOC
    number_of_arms: int = 1
    adaptive_design: bool = False
    dose_escalation: bool = False
    expansion_cohorts: List[str] = field(default_factory=list)
    target_enrollment: int = 0
    enrollment_duration_months: int = 0
    treatment_duration: str = ""
    number_of_sites: int = 0
    countries: List[str] = field(default_factory=list)


@dataclass
class ParsedOncologyProtocol:
    """Complete parsed oncology protocol"""
    metadata: OncologyProtocolMetadata = field(default_factory=OncologyProtocolMetadata)
    indication: CancerIndication = field(default_factory=CancerIndication)
    intervention: Intervention = field(default_factory=Intervention)
    population: PatientPopulation = field(default_factory=PatientPopulation)
    endpoints: EndpointsAndResponse = field(default_factory=EndpointsAndResponse)
    operational: OperationalBurden = field(default_factory=OperationalBurden)
    safety: SafetyMonitoring = field(default_factory=SafetyMonitoring)
    design: TrialDesign = field(default_factory=TrialDesign)
    
    raw_text_preview: str = ""
    parsing_confidence: float = 0.0
    parsing_notes: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metadata": asdict(self.metadata),
            "indication": asdict(self.indication),
            "intervention": asdict(self.intervention),
            "population": asdict(self.population),
            "endpoints": asdict(self.endpoints),
            "operational": asdict(self.operational),
            "safety": asdict(self.safety),
            "design": asdict(self.design),
            "parsing_confidence": self.parsing_confidence,
            "parsing_notes": self.parsing_notes
        }


class OncologyProtocolParser:
    """
    Parses oncology clinical trial protocols using LLM
    Specialized for oncology-specific fields and terminology
    """
    
    ONCOLOGY_EXTRACTION_PROMPT = """You are an expert oncology clinical trial protocol analyst. Extract structured information from this oncology protocol.

Return a JSON object with these oncology-specific fields. Use null for fields you cannot determine.

{
    "metadata": {
        "trial_title": "string",
        "protocol_number": "string",
        "sponsor": "string",
        "phase": "Phase 1 | Phase 1/2 | Phase 2 | Phase 2/3 | Phase 3 | Phase 4",
        "version": "string",
        "version_date": "string"
    },
    "indication": {
        "cancer_type": "breast | lung | colorectal | melanoma | ovarian | prostate | pancreatic | gastric | hepatocellular | renal | bladder | head_and_neck | lymphoma | leukemia | myeloma | other",
        "cancer_subtype": "specific subtype e.g., NSCLC, HER2+ breast, DLBCL",
        "tumor_type": "solid_tumor | hematologic | unknown",
        "histology": "adenocarcinoma | squamous | small_cell | other",
        "stage": "metastatic | locally_advanced | early_stage | any"
    },
    "intervention": {
        "intervention_type": "small_molecule | monoclonal_antibody | immunotherapy | cell_therapy | ADC | bispecific | combination | radiation | other",
        "drug_name": "string",
        "drug_class": "TKI | checkpoint_inhibitor | CDK4_6_inhibitor | PARP_inhibitor | ADC | CAR_T | other",
        "mechanism_of_action": "string",
        "route_of_administration": "oral | IV | SC | IM",
        "dosing_schedule": "string e.g., 'daily', 'q3w', 'BID'",
        "combination_agents": ["list of combination drugs"]
    },
    "population": {
        "line_of_therapy": "1L | 2L | 3L_plus | any | maintenance | adjuvant | neoadjuvant",
        "biomarker_requirements": ["list: HER2+, EGFR_mutant, BRAF_V600E, PD_L1_positive, MSI_H, BRCA_mutant, ALK_positive, ROS1_positive, KRAS_G12C, etc."],
        "biomarker_testing_method": "IHC | FISH | NGS | PCR | ctDNA | not_specified",
        "prior_therapy_required": ["list of required prior therapies"],
        "prior_therapy_excluded": ["list of excluded prior therapies"],
        "washout_periods": {"therapy_type": "duration"},
        "ecog_performance_status": "0 | 0-1 | 0-2 | not_specified",
        "measurable_disease_required": boolean,
        "cns_metastases_allowed": boolean,
        "cns_metastases_conditions": "string if allowed with conditions",
        "age_range": {"min": number, "max": number or null},
        "organ_function_requirements": ["list: adequate hepatic, renal, bone marrow function details"],
        "inclusion_criteria": ["list of key inclusion criteria"],
        "exclusion_criteria": ["list of key exclusion criteria"]
    },
    "endpoints": {
        "primary_endpoint": "OS | PFS | ORR | DOR | DCR | DLT_MTD | safety | PK | other",
        "primary_endpoint_definition": "string",
        "secondary_endpoints": ["list"],
        "exploratory_endpoints": ["list"],
        "response_criteria": "RECIST_1_1 | iRECIST | Lugano | RANO | mRECIST | IMWG | other",
        "imaging_modality": ["CT", "MRI", "PET", "bone_scan"],
        "imaging_frequency": "q6w | q8w | q9w | q12w | other",
        "tumor_assessment_schedule": "string",
        "survival_follow_up": "string"
    },
    "operational": {
        "screening_biopsy_required": boolean,
        "on_treatment_biopsy_required": boolean,
        "progression_biopsy_required": boolean,
        "biopsy_type": "core_needle | excisional | liquid_biopsy | not_required",
        "total_biopsies": number,
        "screening_period_days": number,
        "treatment_visits_per_cycle": number,
        "cycle_length_days": number,
        "total_visits_estimate": number,
        "lab_frequency": "string",
        "lab_tests": ["list of required labs"],
        "ecg_required": boolean,
        "ecg_frequency": "string",
        "echo_muga_required": boolean,
        "echo_muga_frequency": "string",
        "pk_sampling_required": boolean,
        "pk_timepoints_per_cycle": number,
        "hospitalization_required": boolean,
        "central_lab_required": boolean,
        "central_imaging_required": boolean
    },
    "safety": {
        "dlt_assessment_window": "string for Phase 1",
        "dose_escalation_scheme": "3+3 | BOIN | CRM | mTPI | other | not_applicable",
        "dsmb_required": boolean,
        "interim_analyses": number,
        "cardiac_monitoring": boolean,
        "cardiac_monitoring_details": "string",
        "hepatotoxicity_monitoring": boolean,
        "nephrotoxicity_monitoring": boolean,
        "neurotoxicity_monitoring": boolean,
        "pulmonary_monitoring": boolean,
        "irae_monitoring": boolean,
        "cytokine_release_monitoring": boolean,
        "special_safety_concerns": ["list"]
    },
    "design": {
        "design_type": "single_arm | randomized | dose_escalation | basket | umbrella | platform",
        "randomization_ratio": "string e.g., 1:1, 2:1",
        "stratification_factors": ["list"],
        "blinding": "open_label | single_blind | double_blind",
        "control_arm": "none | placebo | active_comparator | SOC",
        "number_of_arms": number,
        "adaptive_design": boolean,
        "dose_escalation": boolean,
        "expansion_cohorts": ["list of expansion cohort descriptions"],
        "target_enrollment": number,
        "enrollment_duration_months": number,
        "treatment_duration": "string",
        "number_of_sites": number,
        "countries": ["list"]
    },
    "parsing_confidence": 0.0 to 1.0,
    "parsing_notes": ["any notes about uncertain extractions"]
}

PROTOCOL TEXT:
"""

    def __init__(self, openai_api_key: Optional[str] = None, model: str = "gpt-4o-mini"):
        """Initialize parser with OpenAI API key"""
        self.api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required for LLM parsing")
        self.client = OpenAI(api_key=self.api_key)
        self.model = model  # Use gpt-4o-mini by default for better rate limits
        
        if fitz is None:
            raise ImportError("PyMuPDF required. Install with: pip install pymupdf")
    
    def extract_text_from_pdf(self, pdf_path: str) -> str:
        """Extract text from PDF file"""
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF not found: {pdf_path}")
        
        doc = fitz.open(pdf_path)
        text_parts = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            text_parts.append(f"\n--- PAGE {page_num + 1} ---\n{text}")
        
        doc.close()
        return "\n".join(text_parts)
    
    def extract_text_from_pdf_bytes(self, pdf_bytes: bytes) -> str:
        """Extract text from PDF bytes"""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            text_parts.append(f"\n--- PAGE {page_num + 1} ---\n{text}")
        
        doc.close()
        return "\n".join(text_parts)
    
    def _parse_with_llm(self, text: str) -> Dict[str, Any]:
        """Send text to LLM for oncology-specific extraction"""
        # Truncate to stay within token limits
        max_chars = 60000  # ~15k tokens, conservative for rate limits
        if len(text) > max_chars:
            # Keep beginning (synopsis, eligibility) and end (assessments, safety)
            text = text[:40000] + "\n\n[... MIDDLE SECTIONS TRUNCATED ...]\n\n" + text[-20000:]
        
        prompt = self.ONCOLOGY_EXTRACTION_PROMPT + text
        
        response = self.client.chat.completions.create(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert oncology clinical trial protocol analyst. Extract structured data accurately. Return only valid JSON. Focus on oncology-specific details like biomarkers, RECIST criteria, and tumor assessments."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.1,
            max_tokens=4000,
            response_format={"type": "json_object"}
        )
        
        result = response.choices[0].message.content
        return json.loads(result)
    
    def _safe_int(self, val, default: int = 0) -> int:
        """Safely convert value to int"""
        if val is None:
            return default
        try:
            return int(val)
        except (TypeError, ValueError):
            return default
    
    def _safe_float(self, val, default: float = 0.0) -> float:
        """Safely convert value to float"""
        if val is None:
            return default
        try:
            return float(val)
        except (TypeError, ValueError):
            return default
    
    def _safe_str(self, val, default: str = "") -> str:
        """Safely convert value to string"""
        if val is None:
            return default
        return str(val)
    
    def _safe_list(self, val, default: list = None) -> list:
        """Safely convert value to list"""
        if default is None:
            default = []
        if val is None:
            return default
        if isinstance(val, list):
            return val
        return default
    
    def _safe_bool(self, val, default: bool = False) -> bool:
        """Safely convert value to bool"""
        if val is None:
            return default
        if isinstance(val, bool):
            return val
        if isinstance(val, str):
            return val.lower() in ('true', 'yes', '1')
        return bool(val)
    
    def _dict_to_protocol(self, data: Dict[str, Any]) -> ParsedOncologyProtocol:
        """Convert dictionary to ParsedOncologyProtocol"""
        protocol = ParsedOncologyProtocol()
        
        # Metadata
        if "metadata" in data and data["metadata"]:
            m = data["metadata"]
            protocol.metadata = OncologyProtocolMetadata(
                trial_title=m.get("trial_title") or "",
                protocol_number=m.get("protocol_number") or "",
                sponsor=m.get("sponsor") or "",
                phase=m.get("phase") or "",
                version=m.get("version") or "",
                version_date=m.get("version_date") or ""
            )
        
        # Indication
        if "indication" in data and data["indication"]:
            i = data["indication"]
            protocol.indication = CancerIndication(
                cancer_type=i.get("cancer_type") or "",
                cancer_subtype=i.get("cancer_subtype") or "",
                tumor_type=i.get("tumor_type") or "",
                histology=i.get("histology") or "",
                stage=i.get("stage") or ""
            )
        
        # Intervention
        if "intervention" in data and data["intervention"]:
            iv = data["intervention"]
            protocol.intervention = Intervention(
                intervention_type=iv.get("intervention_type") or "",
                drug_name=iv.get("drug_name") or "",
                drug_class=iv.get("drug_class") or "",
                mechanism_of_action=iv.get("mechanism_of_action") or "",
                route_of_administration=iv.get("route_of_administration") or "",
                dosing_schedule=iv.get("dosing_schedule") or "",
                combination_agents=iv.get("combination_agents") or []
            )
        
        # Population
        if "population" in data and data["population"]:
            p = data["population"]
            protocol.population = PatientPopulation(
                line_of_therapy=p.get("line_of_therapy") or "",
                biomarker_requirements=p.get("biomarker_requirements") or [],
                biomarker_testing_method=p.get("biomarker_testing_method") or "",
                prior_therapy_required=p.get("prior_therapy_required") or [],
                prior_therapy_excluded=p.get("prior_therapy_excluded") or [],
                washout_periods=p.get("washout_periods") or {},
                ecog_performance_status=p.get("ecog_performance_status") or "",
                measurable_disease_required=p.get("measurable_disease_required", True),
                cns_metastases_allowed=p.get("cns_metastases_allowed", False),
                cns_metastases_conditions=p.get("cns_metastases_conditions") or "",
                age_range=p.get("age_range") or {"min": 18, "max": None},
                organ_function_requirements=p.get("organ_function_requirements") or [],
                inclusion_criteria=p.get("inclusion_criteria") or [],
                exclusion_criteria=p.get("exclusion_criteria") or []
            )
        
        # Endpoints
        if "endpoints" in data and data["endpoints"]:
            e = data["endpoints"]
            protocol.endpoints = EndpointsAndResponse(
                primary_endpoint=e.get("primary_endpoint") or "",
                primary_endpoint_definition=e.get("primary_endpoint_definition") or "",
                secondary_endpoints=e.get("secondary_endpoints") or [],
                exploratory_endpoints=e.get("exploratory_endpoints") or [],
                response_criteria=e.get("response_criteria") or "",
                imaging_modality=e.get("imaging_modality") or [],
                imaging_frequency=e.get("imaging_frequency") or "",
                tumor_assessment_schedule=e.get("tumor_assessment_schedule") or "",
                survival_follow_up=e.get("survival_follow_up") or ""
            )
        
        # Operational
        if "operational" in data and data["operational"]:
            o = data["operational"]
            protocol.operational = OperationalBurden(
                screening_biopsy_required=self._safe_bool(o.get("screening_biopsy_required")),
                on_treatment_biopsy_required=self._safe_bool(o.get("on_treatment_biopsy_required")),
                progression_biopsy_required=self._safe_bool(o.get("progression_biopsy_required")),
                biopsy_type=self._safe_str(o.get("biopsy_type")),
                total_biopsies=self._safe_int(o.get("total_biopsies"), 0),
                screening_period_days=self._safe_int(o.get("screening_period_days"), 28),
                treatment_visits_per_cycle=self._safe_int(o.get("treatment_visits_per_cycle"), 1),
                cycle_length_days=self._safe_int(o.get("cycle_length_days"), 21),
                total_visits_estimate=self._safe_int(o.get("total_visits_estimate"), 0),
                lab_frequency=self._safe_str(o.get("lab_frequency")),
                lab_tests=self._safe_list(o.get("lab_tests")),
                ecg_required=self._safe_bool(o.get("ecg_required")),
                ecg_frequency=self._safe_str(o.get("ecg_frequency")),
                echo_muga_required=self._safe_bool(o.get("echo_muga_required")),
                echo_muga_frequency=self._safe_str(o.get("echo_muga_frequency")),
                pk_sampling_required=self._safe_bool(o.get("pk_sampling_required")),
                pk_timepoints_per_cycle=self._safe_int(o.get("pk_timepoints_per_cycle"), 0),
                hospitalization_required=self._safe_bool(o.get("hospitalization_required")),
                central_lab_required=self._safe_bool(o.get("central_lab_required")),
                central_imaging_required=self._safe_bool(o.get("central_imaging_required"))
            )
        
        # Safety
        if "safety" in data and data["safety"]:
            s = data["safety"]
            protocol.safety = SafetyMonitoring(
                dlt_assessment_window=self._safe_str(s.get("dlt_assessment_window")),
                dose_escalation_scheme=self._safe_str(s.get("dose_escalation_scheme")),
                dsmb_required=self._safe_bool(s.get("dsmb_required")),
                interim_analyses=self._safe_int(s.get("interim_analyses"), 0),
                cardiac_monitoring=self._safe_bool(s.get("cardiac_monitoring")),
                cardiac_monitoring_details=self._safe_str(s.get("cardiac_monitoring_details")),
                hepatotoxicity_monitoring=self._safe_bool(s.get("hepatotoxicity_monitoring")),
                nephrotoxicity_monitoring=self._safe_bool(s.get("nephrotoxicity_monitoring")),
                neurotoxicity_monitoring=self._safe_bool(s.get("neurotoxicity_monitoring")),
                pulmonary_monitoring=self._safe_bool(s.get("pulmonary_monitoring")),
                irae_monitoring=self._safe_bool(s.get("irae_monitoring")),
                cytokine_release_monitoring=self._safe_bool(s.get("cytokine_release_monitoring")),
                special_safety_concerns=self._safe_list(s.get("special_safety_concerns"))
            )
        
        # Design
        if "design" in data and data["design"]:
            d = data["design"]
            protocol.design = TrialDesign(
                design_type=self._safe_str(d.get("design_type")),
                randomization_ratio=self._safe_str(d.get("randomization_ratio")),
                stratification_factors=self._safe_list(d.get("stratification_factors")),
                blinding=self._safe_str(d.get("blinding")),
                control_arm=self._safe_str(d.get("control_arm")),
                number_of_arms=self._safe_int(d.get("number_of_arms"), 1),
                adaptive_design=self._safe_bool(d.get("adaptive_design")),
                dose_escalation=self._safe_bool(d.get("dose_escalation")),
                expansion_cohorts=self._safe_list(d.get("expansion_cohorts")),
                target_enrollment=self._safe_int(d.get("target_enrollment"), 0),
                enrollment_duration_months=self._safe_int(d.get("enrollment_duration_months"), 0),
                treatment_duration=self._safe_str(d.get("treatment_duration")),
                number_of_sites=self._safe_int(d.get("number_of_sites"), 0),
                countries=self._safe_list(d.get("countries"))
            )
        
        protocol.parsing_confidence = self._safe_float(data.get("parsing_confidence"), 0.0)
        protocol.parsing_notes = self._safe_list(data.get("parsing_notes"))
        
        return protocol
    
    def parse_pdf(self, pdf_path: str) -> ParsedOncologyProtocol:
        """Parse an oncology protocol PDF"""
        raw_text = self.extract_text_from_pdf(pdf_path)
        parsed_data = self._parse_with_llm(raw_text)
        protocol = self._dict_to_protocol(parsed_data)
        protocol.raw_text_preview = raw_text[:5000]
        return protocol
    
    def parse_pdf_bytes(self, pdf_bytes: bytes) -> ParsedOncologyProtocol:
        """Parse oncology protocol from PDF bytes"""
        raw_text = self.extract_text_from_pdf_bytes(pdf_bytes)
        parsed_data = self._parse_with_llm(raw_text)
        protocol = self._dict_to_protocol(parsed_data)
        protocol.raw_text_preview = raw_text[:5000]
        return protocol
    
    def parse_text(self, protocol_text: str) -> ParsedOncologyProtocol:
        """Parse oncology protocol from raw text"""
        parsed_data = self._parse_with_llm(protocol_text)
        protocol = self._dict_to_protocol(parsed_data)
        protocol.raw_text_preview = protocol_text[:5000]
        return protocol
