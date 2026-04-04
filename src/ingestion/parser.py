"""Parse ClinicalTrials.gov API responses into database models."""

import re
from typing import Any


def normalize_name(name: str | None) -> str | None:
    """Normalize a name for matching (lowercase, remove titles, extra spaces)."""
    if not name:
        return None
    
    # Remove common titles
    titles = [
        r'\bMD\b', r'\bM\.D\.\b', r'\bPhD\b', r'\bPh\.D\.\b', 
        r'\bDO\b', r'\bD\.O\.\b', r'\bMPH\b', r'\bM\.P\.H\.\b',
        r'\bDr\.\b', r'\bProf\.\b', r'\bProfessor\b',
    ]
    
    result = name
    for title in titles:
        result = re.sub(title, '', result, flags=re.IGNORECASE)
    
    # Remove extra whitespace and lowercase
    result = ' '.join(result.split()).lower().strip()
    
    # Remove trailing/leading punctuation
    result = result.strip('.,;:')
    
    return result if result else None


def normalize_facility_name(name: str | None) -> str | None:
    """Normalize facility name for matching."""
    if not name:
        return None
    
    result = name.lower()
    
    # Common abbreviations
    replacements = [
        (r'\buniv\.?\b', 'university'),
        (r'\bhosp\.?\b', 'hospital'),
        (r'\bmed\.?\b', 'medical'),
        (r'\bctr\.?\b', 'center'),
        (r'\binst\.?\b', 'institute'),
    ]
    
    for pattern, replacement in replacements:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    
    # Remove extra whitespace
    result = ' '.join(result.split()).strip()
    
    return result if result else None


def safe_get(data: dict, *keys, default=None) -> Any:
    """Safely get nested dictionary values."""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key, default)
        else:
            return default
    return data


def parse_date(date_str: str | None) -> str | None:
    """
    Parse date string from CT.gov format to ISO format.
    
    CT.gov dates can be "YYYY-MM-DD", "YYYY-MM", or "YYYY".
    PostgreSQL DATE requires full "YYYY-MM-DD" format.
    """
    if not date_str:
        return None
    
    parts = date_str.split('-')
    
    if len(parts) == 3:
        # Already full date: "YYYY-MM-DD"
        return date_str
    elif len(parts) == 2:
        # Partial date: "YYYY-MM" -> "YYYY-MM-01"
        return f"{date_str}-01"
    elif len(parts) == 1:
        # Year only: "YYYY" -> "YYYY-01-01"
        return f"{date_str}-01-01"
    
    return date_str


def condense_study_json(study: dict) -> dict:
    """
    Condense study JSON to only essential modules for storage.
    Reduces storage by ~60% while keeping data needed for future re-parsing.
    """
    protocol = study.get("protocolSection", {})
    
    # Modules we need to keep
    keep_modules = [
        "identificationModule",
        "statusModule",
        "sponsorCollaboratorsModule",
        "conditionsModule",
        "designModule",
        "contactsLocationsModule",
        "descriptionModule",  # Keep briefSummary for search
    ]
    
    condensed_protocol = {}
    for module in keep_modules:
        if module in protocol:
            if module == "descriptionModule":
                # Only keep briefSummary, drop detailedDescription
                desc = protocol[module]
                condensed_protocol[module] = {
                    "briefSummary": desc.get("briefSummary")
                }
            else:
                condensed_protocol[module] = protocol[module]
    
    return {
        "protocolSection": condensed_protocol,
        "hasResults": study.get("hasResults", False),
    }


def parse_study(study: dict) -> dict:
    """
    Parse a study from CT.gov API response into our schema format.
    
    Returns dict with keys: trial, sites, investigators
    """
    protocol = study.get("protocolSection", {})
    
    # Identification
    id_module = protocol.get("identificationModule", {})
    nct_id = id_module.get("nctId")
    
    # Description
    desc_module = protocol.get("descriptionModule", {})
    
    # Conditions
    conditions_module = protocol.get("conditionsModule", {})
    conditions = conditions_module.get("conditions", [])
    
    # Design
    design_module = protocol.get("designModule", {})
    phases = design_module.get("phases", [])
    phase = phases[0] if phases else None
    
    # Status
    status_module = protocol.get("statusModule", {})
    
    # Enrollment
    enrollment_info = design_module.get("enrollmentInfo", {})
    
    # Sponsor
    sponsor_module = protocol.get("sponsorCollaboratorsModule", {})
    lead_sponsor = sponsor_module.get("leadSponsor", {})
    
    # Contacts & Locations
    contacts_module = protocol.get("contactsLocationsModule", {})
    
    # Build trial record
    trial = {
        "nct_id": nct_id,
        "brief_title": id_module.get("briefTitle"),
        "official_title": id_module.get("officialTitle"),
        "brief_summary": desc_module.get("briefSummary"),
        "conditions": conditions if conditions else None,
        "phase": phase,
        "study_type": design_module.get("studyType"),
        "overall_status": status_module.get("overallStatus"),
        "start_date": parse_date(safe_get(status_module, "startDateStruct", "date")),
        "completion_date": parse_date(safe_get(status_module, "completionDateStruct", "date")),
        "primary_completion_date": parse_date(safe_get(status_module, "primaryCompletionDateStruct", "date")),
        "enrollment": enrollment_info.get("count"),
        "enrollment_type": enrollment_info.get("type"),
        "lead_sponsor_name": lead_sponsor.get("name"),
        "lead_sponsor_class": lead_sponsor.get("class"),
        "last_update_posted": parse_date(safe_get(status_module, "lastUpdatePostDateStruct", "date")),
        "raw_json": condense_study_json(study),  # Store condensed JSON
    }
    
    # Parse sites (locations) with their contacts
    sites = []
    site_contacts = []  # Site-level investigators from location.contacts
    locations = contacts_module.get("locations", [])
    
    for loc_idx, loc in enumerate(locations):
        site = {
            "facility_name": loc.get("facility"),
            "facility_name_normalized": normalize_facility_name(loc.get("facility")),
            "city": loc.get("city"),
            "state": loc.get("state"),
            "country": loc.get("country"),
            "zip": loc.get("zip"),
            "recruitment_status": loc.get("status"),
            "_location_index": loc_idx,  # Track index for linking
        }
        if site["facility_name"]:
            sites.append(site)
            
            # Extract site-level contacts (these are site-specific PIs/contacts)
            for contact in loc.get("contacts", []):
                if contact.get("name"):
                    site_contacts.append({
                        "full_name": contact.get("name"),
                        "name_normalized": normalize_name(contact.get("name")),
                        "role": contact.get("role"),
                        "phone": contact.get("phone"),
                        "email": contact.get("email"),
                        "_site_index": loc_idx,  # Link to specific site
                    })
    
    # Parse overall officials (study-level investigators)
    overall_officials = []
    officials = contacts_module.get("overallOfficials", [])
    for official in officials:
        inv = {
            "full_name": official.get("name"),
            "name_normalized": normalize_name(official.get("name")),
            "role": official.get("role"),
            "affiliation": official.get("affiliation"),
            "affiliation_normalized": normalize_facility_name(official.get("affiliation")),
        }
        if inv["full_name"]:
            overall_officials.append(inv)
    
    return {
        "trial": trial,
        "sites": sites,
        "overall_officials": overall_officials,  # Study-level PIs
        "site_contacts": site_contacts,  # Site-level contacts with _site_index
    }


def parse_studies_batch(studies: list[dict]) -> list[dict]:
    """Parse a batch of studies."""
    return [parse_study(study) for study in studies]
