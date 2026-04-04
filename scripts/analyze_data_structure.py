"""Analyze ClinicalTrials.gov data to understand PI/site linkage availability."""

import httpx
import json
from collections import Counter

API_URL = "https://clinicaltrials.gov/api/v2/studies"

def fetch_sample(count: int = 100) -> list[dict]:
    """Fetch a sample of studies from the API."""
    params = {
        "format": "json",
        "pageSize": min(count, 1000),
    }
    
    response = httpx.get(API_URL, params=params, timeout=60.0)
    response.raise_for_status()
    data = response.json()
    return data.get("studies", [])


def analyze_studies(studies: list[dict]) -> dict:
    """Analyze PI and site data availability."""
    stats = {
        "total_studies": len(studies),
        "has_overall_officials": 0,
        "has_locations": 0,
        "has_location_contacts": 0,
        "overall_officials_count": [],
        "locations_count": [],
        "location_contacts_count": [],
        "affiliation_matches_facility": 0,
    }
    
    sample_with_contacts = []
    sample_officials = []
    
    for study in studies:
        protocol = study.get("protocolSection", {})
        contacts_module = protocol.get("contactsLocationsModule", {})
        
        # Check overallOfficials
        officials = contacts_module.get("overallOfficials", [])
        if officials:
            stats["has_overall_officials"] += 1
            stats["overall_officials_count"].append(len(officials))
            if len(sample_officials) < 3:
                sample_officials.append(officials)
        
        # Check locations
        locations = contacts_module.get("locations", [])
        if locations:
            stats["has_locations"] += 1
            stats["locations_count"].append(len(locations))
            
            # Check if any location has contacts
            locations_with_contacts = [loc for loc in locations if loc.get("contacts")]
            if locations_with_contacts:
                stats["has_location_contacts"] += 1
                stats["location_contacts_count"].append(len(locations_with_contacts))
                if len(sample_with_contacts) < 3:
                    sample_with_contacts.append(locations_with_contacts[0])
        
        # Check if any official's affiliation matches a facility name
        for official in officials:
            affiliation = (official.get("affiliation") or "").lower()
            for loc in locations:
                facility = (loc.get("facility") or "").lower()
                if affiliation and facility and (affiliation in facility or facility in affiliation):
                    stats["affiliation_matches_facility"] += 1
                    break
    
    return stats, sample_officials, sample_with_contacts


def main():
    print("Fetching 1000 studies from ClinicalTrials.gov API...")
    studies = fetch_sample(1000)
    
    print(f"Analyzing {len(studies)} studies...\n")
    stats, sample_officials, sample_contacts = analyze_studies(studies)
    
    print("=" * 60)
    print("DATA AVAILABILITY ANALYSIS")
    print("=" * 60)
    
    total = stats["total_studies"]
    
    print(f"\nTotal studies analyzed: {total}")
    print(f"\nOverall Officials (study-level PIs):")
    print(f"  - Studies with overallOfficials: {stats['has_overall_officials']} ({100*stats['has_overall_officials']/total:.1f}%)")
    if stats["overall_officials_count"]:
        print(f"  - Avg officials per study: {sum(stats['overall_officials_count'])/len(stats['overall_officials_count']):.1f}")
    
    print(f"\nLocations (sites):")
    print(f"  - Studies with locations: {stats['has_locations']} ({100*stats['has_locations']/total:.1f}%)")
    if stats["locations_count"]:
        print(f"  - Avg locations per study: {sum(stats['locations_count'])/len(stats['locations_count']):.1f}")
    
    print(f"\nLocation Contacts (site-level contacts):")
    print(f"  - Studies with location contacts: {stats['has_location_contacts']} ({100*stats['has_location_contacts']/total:.1f}%)")
    if stats["location_contacts_count"]:
        print(f"  - Avg locations with contacts: {sum(stats['location_contacts_count'])/len(stats['location_contacts_count']):.1f}")
    
    print(f"\nAffiliation-Facility Matching:")
    print(f"  - Officials whose affiliation matches a facility: {stats['affiliation_matches_facility']} ({100*stats['affiliation_matches_facility']/stats['has_overall_officials']:.1f}% of studies with officials)")
    
    print("\n" + "=" * 60)
    print("SAMPLE DATA")
    print("=" * 60)
    
    print("\nSample overallOfficials:")
    for i, officials in enumerate(sample_officials, 1):
        print(f"\n  Study {i}:")
        for off in officials[:2]:
            print(f"    - {off.get('name')} | {off.get('role')} | {off.get('affiliation')}")
    
    print("\nSample location contacts:")
    for i, loc in enumerate(sample_contacts, 1):
        print(f"\n  Location {i}: {loc.get('facility')}")
        for contact in loc.get("contacts", [])[:2]:
            print(f"    - {contact.get('name')} | {contact.get('role')} | {contact.get('phone')}")


if __name__ == "__main__":
    main()
