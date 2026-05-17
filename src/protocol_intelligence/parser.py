"""
Protocol Parser Module
Extracts structured data from clinical trial protocol PDFs using LLM
"""

import os
import json
import re
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
from openai import OpenAI

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None


@dataclass
class ProtocolMetadata:
    """Basic protocol identification info"""
    protocol_number: str = ""
    protocol_title: str = ""
    sponsor: str = ""
    phase: str = ""
    indication: str = ""
    therapeutic_area: str = ""
    drug_name: str = ""
    version: str = ""
    version_date: str = ""


@dataclass
class InclusionExclusionCriteria:
    """Eligibility criteria"""
    inclusion_criteria: List[str] = None
    exclusion_criteria: List[str] = None
    age_range: Dict[str, int] = None
    gender: str = "all"
    requires_biomarker: bool = False
    biomarker_details: str = ""
    requires_prior_therapy: bool = False
    prior_therapy_details: str = ""
    
    def __post_init__(self):
        if self.inclusion_criteria is None:
            self.inclusion_criteria = []
        if self.exclusion_criteria is None:
            self.exclusion_criteria = []
        if self.age_range is None:
            self.age_range = {"min": 18, "max": None}


@dataclass
class StudyDesign:
    """Study design parameters"""
    design_type: str = ""  # parallel, crossover, single-arm
    randomization: bool = False
    blinding: str = ""  # open-label, single-blind, double-blind
    control_type: str = ""  # placebo, active, none
    number_of_arms: int = 1
    treatment_duration_weeks: int = 0
    follow_up_duration_weeks: int = 0
    adaptive_design: bool = False
    dose_escalation: bool = False


@dataclass
class VisitSchedule:
    """Visit and assessment schedule"""
    screening_visits: int = 1
    treatment_visits: int = 0
    follow_up_visits: int = 0
    total_visits: int = 0
    visit_frequency: str = ""  # weekly, biweekly, monthly
    home_visits_allowed: bool = False
    telemedicine_allowed: bool = False


@dataclass
class Assessments:
    """Required assessments and procedures"""
    lab_tests: List[str] = None
    imaging_studies: List[str] = None
    ecg_required: bool = False
    ecg_frequency: str = ""
    pk_sampling: bool = False
    pk_timepoints: int = 0
    biopsies_required: bool = False
    biopsy_count: int = 0
    patient_reported_outcomes: List[str] = None
    special_equipment: List[str] = None
    
    def __post_init__(self):
        if self.lab_tests is None:
            self.lab_tests = []
        if self.imaging_studies is None:
            self.imaging_studies = []
        if self.patient_reported_outcomes is None:
            self.patient_reported_outcomes = []
        if self.special_equipment is None:
            self.special_equipment = []


@dataclass
class SafetyMonitoring:
    """Safety monitoring requirements"""
    dsmb_required: bool = False
    interim_analyses: int = 0
    stopping_rules: bool = False
    dose_limiting_toxicity: bool = False
    cardiac_monitoring: bool = False
    liver_monitoring: bool = False
    renal_monitoring: bool = False
    cns_monitoring: bool = False
    special_safety_concerns: List[str] = None
    
    def __post_init__(self):
        if self.special_safety_concerns is None:
            self.special_safety_concerns = []


@dataclass
class Endpoints:
    """Study endpoints"""
    primary_endpoints: List[str] = None
    secondary_endpoints: List[str] = None
    exploratory_endpoints: List[str] = None
    primary_endpoint_type: str = ""  # efficacy, safety, pk
    
    def __post_init__(self):
        if self.primary_endpoints is None:
            self.primary_endpoints = []
        if self.secondary_endpoints is None:
            self.secondary_endpoints = []
        if self.exploratory_endpoints is None:
            self.exploratory_endpoints = []


@dataclass
class SampleSize:
    """Sample size and enrollment"""
    target_enrollment: int = 0
    number_of_sites: int = 0
    enrollment_duration_months: int = 0
    countries: List[str] = None
    
    def __post_init__(self):
        if self.countries is None:
            self.countries = []


@dataclass
class ParsedProtocol:
    """Complete parsed protocol structure"""
    metadata: ProtocolMetadata = None
    eligibility: InclusionExclusionCriteria = None
    study_design: StudyDesign = None
    visit_schedule: VisitSchedule = None
    assessments: Assessments = None
    safety_monitoring: SafetyMonitoring = None
    endpoints: Endpoints = None
    sample_size: SampleSize = None
    raw_text: str = ""
    parsing_confidence: float = 0.0
    parsing_notes: List[str] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = ProtocolMetadata()
        if self.eligibility is None:
            self.eligibility = InclusionExclusionCriteria()
        if self.study_design is None:
            self.study_design = StudyDesign()
        if self.visit_schedule is None:
            self.visit_schedule = VisitSchedule()
        if self.assessments is None:
            self.assessments = Assessments()
        if self.safety_monitoring is None:
            self.safety_monitoring = SafetyMonitoring()
        if self.endpoints is None:
            self.endpoints = Endpoints()
        if self.sample_size is None:
            self.sample_size = SampleSize()
        if self.parsing_notes is None:
            self.parsing_notes = []
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            "metadata": asdict(self.metadata),
            "eligibility": asdict(self.eligibility),
            "study_design": asdict(self.study_design),
            "visit_schedule": asdict(self.visit_schedule),
            "assessments": asdict(self.assessments),
            "safety_monitoring": asdict(self.safety_monitoring),
            "endpoints": asdict(self.endpoints),
            "sample_size": asdict(self.sample_size),
            "parsing_confidence": self.parsing_confidence,
            "parsing_notes": self.parsing_notes
        }


class ProtocolParser:
    """
    Parses clinical trial protocol PDFs into structured data using LLM
    """
    
    EXTRACTION_PROMPT = """You are an expert clinical trial protocol analyst. Extract structured information from the following clinical trial protocol text.

Return a JSON object with the following structure. For any field you cannot determine from the text, use null or empty arrays/strings as appropriate.

{
    "metadata": {
        "protocol_number": "string",
        "protocol_title": "string", 
        "sponsor": "string",
        "phase": "string (Phase 1, Phase 2, Phase 3, Phase 4, or combination)",
        "indication": "string",
        "therapeutic_area": "string (oncology, cardiology, neurology, etc.)",
        "drug_name": "string",
        "version": "string",
        "version_date": "string"
    },
    "eligibility": {
        "inclusion_criteria": ["list of inclusion criteria as strings"],
        "exclusion_criteria": ["list of exclusion criteria as strings"],
        "age_range": {"min": number, "max": number or null},
        "gender": "all/male/female",
        "requires_biomarker": boolean,
        "biomarker_details": "string describing required biomarkers",
        "requires_prior_therapy": boolean,
        "prior_therapy_details": "string"
    },
    "study_design": {
        "design_type": "parallel/crossover/single-arm/factorial",
        "randomization": boolean,
        "blinding": "open-label/single-blind/double-blind/triple-blind",
        "control_type": "placebo/active/none/standard-of-care",
        "number_of_arms": number,
        "treatment_duration_weeks": number,
        "follow_up_duration_weeks": number,
        "adaptive_design": boolean,
        "dose_escalation": boolean
    },
    "visit_schedule": {
        "screening_visits": number,
        "treatment_visits": number,
        "follow_up_visits": number,
        "total_visits": number,
        "visit_frequency": "weekly/biweekly/monthly/variable",
        "home_visits_allowed": boolean,
        "telemedicine_allowed": boolean
    },
    "assessments": {
        "lab_tests": ["list of required lab tests"],
        "imaging_studies": ["list: CT, MRI, PET, X-ray, ultrasound, ECHO, etc."],
        "ecg_required": boolean,
        "ecg_frequency": "string",
        "pk_sampling": boolean,
        "pk_timepoints": number,
        "biopsies_required": boolean,
        "biopsy_count": number,
        "patient_reported_outcomes": ["list of PRO instruments"],
        "special_equipment": ["any special equipment needed at sites"]
    },
    "safety_monitoring": {
        "dsmb_required": boolean,
        "interim_analyses": number,
        "stopping_rules": boolean,
        "dose_limiting_toxicity": boolean,
        "cardiac_monitoring": boolean,
        "liver_monitoring": boolean,
        "renal_monitoring": boolean,
        "cns_monitoring": boolean,
        "special_safety_concerns": ["list of specific safety concerns"]
    },
    "endpoints": {
        "primary_endpoints": ["list of primary endpoints"],
        "secondary_endpoints": ["list of secondary endpoints"],
        "exploratory_endpoints": ["list of exploratory/biomarker endpoints"],
        "primary_endpoint_type": "efficacy/safety/pk/tolerability"
    },
    "sample_size": {
        "target_enrollment": number,
        "number_of_sites": number,
        "enrollment_duration_months": number,
        "countries": ["list of countries"]
    },
    "parsing_confidence": number between 0 and 1,
    "parsing_notes": ["any notes about uncertain extractions or missing information"]
}

PROTOCOL TEXT:
"""

    def __init__(self, openai_api_key: Optional[str] = None):
        """Initialize parser with OpenAI API key"""
        self.api_key = openai_api_key or os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OpenAI API key required for LLM parsing")
        self.client = OpenAI(api_key=self.api_key)
        
        if fitz is None:
            raise ImportError("PyMuPDF (fitz) required for PDF parsing. Install with: pip install pymupdf")
    
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
        """Extract text from PDF bytes (for uploaded files)"""
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text_parts = []
        
        for page_num in range(len(doc)):
            page = doc[page_num]
            text = page.get_text()
            text_parts.append(f"\n--- PAGE {page_num + 1} ---\n{text}")
        
        doc.close()
        return "\n".join(text_parts)
    
    def _chunk_text(self, text: str, max_tokens: int = 100000) -> List[str]:
        """Split text into chunks that fit within token limits"""
        # Rough estimate: 1 token ≈ 4 characters
        max_chars = max_tokens * 4
        
        if len(text) <= max_chars:
            return [text]
        
        chunks = []
        current_chunk = ""
        
        # Split by page markers
        pages = re.split(r'--- PAGE \d+ ---', text)
        
        for page in pages:
            if len(current_chunk) + len(page) > max_chars:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = page
            else:
                current_chunk += page
        
        if current_chunk:
            chunks.append(current_chunk)
        
        return chunks
    
    def _parse_with_llm(self, text: str) -> Dict[str, Any]:
        """Send text to LLM for structured extraction"""
        # Truncate if too long - be conservative for rate limits
        max_chars = 80000  # ~20k tokens for input, leaving room for output and rate limits
        if len(text) > max_chars:
            # Keep beginning (metadata, synopsis, eligibility) and sample from end
            text = text[:50000] + "\n\n[... TRUNCATED ...]\n\n" + text[-30000:]
        
        prompt = self.EXTRACTION_PROMPT + text
        
        response = self.client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert clinical trial protocol analyst. Extract structured data from protocols accurately. Return only valid JSON."
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
    
    def _dict_to_parsed_protocol(self, data: Dict[str, Any]) -> ParsedProtocol:
        """Convert dictionary to ParsedProtocol dataclass"""
        protocol = ParsedProtocol()
        
        # Metadata
        if "metadata" in data:
            m = data["metadata"]
            protocol.metadata = ProtocolMetadata(
                protocol_number=m.get("protocol_number", ""),
                protocol_title=m.get("protocol_title", ""),
                sponsor=m.get("sponsor", ""),
                phase=m.get("phase", ""),
                indication=m.get("indication", ""),
                therapeutic_area=m.get("therapeutic_area", ""),
                drug_name=m.get("drug_name", ""),
                version=m.get("version", ""),
                version_date=m.get("version_date", "")
            )
        
        # Eligibility
        if "eligibility" in data:
            e = data["eligibility"]
            protocol.eligibility = InclusionExclusionCriteria(
                inclusion_criteria=e.get("inclusion_criteria", []),
                exclusion_criteria=e.get("exclusion_criteria", []),
                age_range=e.get("age_range", {"min": 18, "max": None}),
                gender=e.get("gender", "all"),
                requires_biomarker=e.get("requires_biomarker", False),
                biomarker_details=e.get("biomarker_details", ""),
                requires_prior_therapy=e.get("requires_prior_therapy", False),
                prior_therapy_details=e.get("prior_therapy_details", "")
            )
        
        # Study Design
        if "study_design" in data:
            s = data["study_design"]
            protocol.study_design = StudyDesign(
                design_type=s.get("design_type", ""),
                randomization=s.get("randomization", False),
                blinding=s.get("blinding", ""),
                control_type=s.get("control_type", ""),
                number_of_arms=s.get("number_of_arms", 1),
                treatment_duration_weeks=s.get("treatment_duration_weeks", 0),
                follow_up_duration_weeks=s.get("follow_up_duration_weeks", 0),
                adaptive_design=s.get("adaptive_design", False),
                dose_escalation=s.get("dose_escalation", False)
            )
        
        # Visit Schedule
        if "visit_schedule" in data:
            v = data["visit_schedule"]
            protocol.visit_schedule = VisitSchedule(
                screening_visits=v.get("screening_visits", 1),
                treatment_visits=v.get("treatment_visits", 0),
                follow_up_visits=v.get("follow_up_visits", 0),
                total_visits=v.get("total_visits", 0),
                visit_frequency=v.get("visit_frequency", ""),
                home_visits_allowed=v.get("home_visits_allowed", False),
                telemedicine_allowed=v.get("telemedicine_allowed", False)
            )
        
        # Assessments
        if "assessments" in data:
            a = data["assessments"]
            protocol.assessments = Assessments(
                lab_tests=a.get("lab_tests", []),
                imaging_studies=a.get("imaging_studies", []),
                ecg_required=a.get("ecg_required", False),
                ecg_frequency=a.get("ecg_frequency", ""),
                pk_sampling=a.get("pk_sampling", False),
                pk_timepoints=a.get("pk_timepoints", 0),
                biopsies_required=a.get("biopsies_required", False),
                biopsy_count=a.get("biopsy_count", 0),
                patient_reported_outcomes=a.get("patient_reported_outcomes", []),
                special_equipment=a.get("special_equipment", [])
            )
        
        # Safety Monitoring
        if "safety_monitoring" in data:
            sm = data["safety_monitoring"]
            protocol.safety_monitoring = SafetyMonitoring(
                dsmb_required=sm.get("dsmb_required", False),
                interim_analyses=sm.get("interim_analyses", 0),
                stopping_rules=sm.get("stopping_rules", False),
                dose_limiting_toxicity=sm.get("dose_limiting_toxicity", False),
                cardiac_monitoring=sm.get("cardiac_monitoring", False),
                liver_monitoring=sm.get("liver_monitoring", False),
                renal_monitoring=sm.get("renal_monitoring", False),
                cns_monitoring=sm.get("cns_monitoring", False),
                special_safety_concerns=sm.get("special_safety_concerns", [])
            )
        
        # Endpoints
        if "endpoints" in data:
            ep = data["endpoints"]
            protocol.endpoints = Endpoints(
                primary_endpoints=ep.get("primary_endpoints", []),
                secondary_endpoints=ep.get("secondary_endpoints", []),
                exploratory_endpoints=ep.get("exploratory_endpoints", []),
                primary_endpoint_type=ep.get("primary_endpoint_type", "")
            )
        
        # Sample Size
        if "sample_size" in data:
            ss = data["sample_size"]
            protocol.sample_size = SampleSize(
                target_enrollment=ss.get("target_enrollment", 0),
                number_of_sites=ss.get("number_of_sites", 0),
                enrollment_duration_months=ss.get("enrollment_duration_months", 0),
                countries=ss.get("countries", [])
            )
        
        protocol.parsing_confidence = data.get("parsing_confidence", 0.0)
        protocol.parsing_notes = data.get("parsing_notes", [])
        
        return protocol
    
    def parse_pdf(self, pdf_path: str) -> ParsedProtocol:
        """Parse a protocol PDF file and return structured data"""
        # Extract text
        raw_text = self.extract_text_from_pdf(pdf_path)
        
        # Parse with LLM
        parsed_data = self._parse_with_llm(raw_text)
        
        # Convert to dataclass
        protocol = self._dict_to_parsed_protocol(parsed_data)
        protocol.raw_text = raw_text[:10000]  # Store truncated raw text
        
        return protocol
    
    def parse_pdf_bytes(self, pdf_bytes: bytes) -> ParsedProtocol:
        """Parse protocol from PDF bytes (for uploaded files)"""
        # Extract text
        raw_text = self.extract_text_from_pdf_bytes(pdf_bytes)
        
        # Parse with LLM
        parsed_data = self._parse_with_llm(raw_text)
        
        # Convert to dataclass
        protocol = self._dict_to_parsed_protocol(parsed_data)
        protocol.raw_text = raw_text[:10000]
        
        return protocol
    
    def parse_text(self, protocol_text: str) -> ParsedProtocol:
        """Parse protocol from raw text"""
        parsed_data = self._parse_with_llm(protocol_text)
        protocol = self._dict_to_parsed_protocol(parsed_data)
        protocol.raw_text = protocol_text[:10000]
        return protocol
