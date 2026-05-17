"""
Protocol Recommender Module
Generates PI and site recommendations based on protocol requirements
"""

import os
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, asdict

from .parser import ParsedProtocol
from .scoring import ProtocolScores


@dataclass
class PIRecommendation:
    """A recommended PI for the protocol"""
    investigator_id: str
    full_name: str
    institution: str
    match_score: float  # 0-100
    match_reasons: List[str]
    experience_summary: Dict[str, Any]
    contact_info: Optional[Dict[str, str]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class SiteRecommendation:
    """A recommended site for the protocol"""
    site_name: str
    location: str
    match_score: float
    match_reasons: List[str]
    capabilities: List[str]
    past_performance: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ProtocolRecommendations:
    """Complete recommendations for a protocol"""
    protocol_id: str
    recommended_pis: List[PIRecommendation]
    recommended_sites: List[SiteRecommendation]
    feasibility_summary: Dict[str, Any]
    execution_recommendations: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "protocol_id": self.protocol_id,
            "recommended_pis": [pi.to_dict() for pi in self.recommended_pis],
            "recommended_sites": [site.to_dict() for site in self.recommended_sites],
            "feasibility_summary": self.feasibility_summary,
            "execution_recommendations": self.execution_recommendations
        }


class ProtocolRecommender:
    """
    Generates PI and site recommendations based on protocol analysis
    Integrates with existing investigator database
    """
    
    def __init__(self, supabase_client=None):
        """
        Initialize recommender with optional Supabase client
        If not provided, will attempt to create one
        """
        self.supabase = supabase_client
        if self.supabase is None:
            try:
                from src.db.supabase_client import get_supabase_client
                self.supabase = get_supabase_client()
            except Exception:
                pass
    
    def _build_pi_query_filters(self, protocol: ParsedProtocol, scores: ProtocolScores) -> Dict[str, Any]:
        """
        Build query filters for finding matching PIs
        """
        filters = {}
        
        # Therapeutic area mapping to specialties
        ta = protocol.metadata.therapeutic_area.lower() if protocol.metadata.therapeutic_area else ""
        specialty_mapping = {
            "oncology": ["oncology", "hematology", "medical oncology"],
            "cardiology": ["cardiology", "cardiovascular"],
            "neurology": ["neurology", "psychiatry"],
            "immunology": ["immunology", "rheumatology", "allergy"],
            "infectious": ["infectious disease", "virology"],
            "endocrinology": ["endocrinology", "diabetes"],
            "gastroenterology": ["gastroenterology", "hepatology"],
            "respiratory": ["pulmonology", "respiratory"],
            "dermatology": ["dermatology"],
        }
        
        for key, specialties in specialty_mapping.items():
            if key in ta:
                filters["specialties"] = specialties
                break
        
        # Experience requirements from PI profile
        pi_profile = scores.recommended_pi_profile
        filters["min_publications"] = pi_profile.get("minimum_publications", 5)
        filters["min_trials"] = pi_profile.get("minimum_trials_experience", 3)
        
        # Phase experience
        phase = protocol.metadata.phase.lower() if protocol.metadata.phase else ""
        if "1" in phase:
            filters["phase_experience"] = ["phase 1", "phase 1/2"]
        elif "2" in phase:
            filters["phase_experience"] = ["phase 2", "phase 1/2", "phase 2/3"]
        elif "3" in phase:
            filters["phase_experience"] = ["phase 3", "phase 2/3"]
        
        return filters
    
    def _calculate_pi_match_score(
        self, 
        investigator: Dict[str, Any], 
        protocol: ParsedProtocol,
        scores: ProtocolScores
    ) -> tuple[float, List[str]]:
        """
        Calculate match score between an investigator and protocol requirements
        Returns (score, list of match reasons)
        """
        score = 50  # Base score
        reasons = []
        
        # Publication count
        pub_count = investigator.get("publication_count", 0) or 0
        min_pubs = scores.recommended_pi_profile.get("minimum_publications", 5)
        if pub_count >= min_pubs * 2:
            score += 15
            reasons.append(f"Strong publication record ({pub_count} publications)")
        elif pub_count >= min_pubs:
            score += 8
            reasons.append(f"Adequate publication record ({pub_count} publications)")
        
        # H-index
        h_index = investigator.get("h_index", 0) or 0
        if h_index >= 30:
            score += 15
            reasons.append(f"High h-index ({h_index})")
        elif h_index >= 15:
            score += 8
            reasons.append(f"Good h-index ({h_index})")
        elif h_index >= 5:
            score += 3
        
        # Therapeutic area match
        ta = protocol.metadata.therapeutic_area.lower() if protocol.metadata.therapeutic_area else ""
        inv_specialties = investigator.get("specialties", []) or []
        if isinstance(inv_specialties, str):
            inv_specialties = [inv_specialties]
        
        for specialty in inv_specialties:
            if specialty and ta and specialty.lower() in ta:
                score += 15
                reasons.append(f"Specialty match: {specialty}")
                break
        
        # Trial experience (from works_count as proxy)
        works_count = investigator.get("works_count", 0) or 0
        if works_count >= 100:
            score += 10
            reasons.append("Extensive research experience")
        elif works_count >= 50:
            score += 5
            reasons.append("Good research experience")
        
        # Institution type (academic medical centers preferred for complex trials)
        institution = investigator.get("institution", "") or ""
        if scores.overall_complexity > 60:
            academic_keywords = ["university", "medical center", "hospital", "institute"]
            if any(kw in institution.lower() for kw in academic_keywords):
                score += 10
                reasons.append("Academic medical center")
        
        # Citation impact
        cited_by = investigator.get("cited_by_count", 0) or 0
        if cited_by >= 5000:
            score += 10
            reasons.append("High citation impact")
        elif cited_by >= 1000:
            score += 5
        
        # Cap score at 100
        score = min(100, max(0, score))
        
        return score, reasons
    
    async def find_matching_pis(
        self,
        protocol: ParsedProtocol,
        scores: ProtocolScores,
        limit: int = 10
    ) -> List[PIRecommendation]:
        """
        Find PIs matching protocol requirements from database
        """
        if self.supabase is None:
            return []
        
        try:
            # Build query based on protocol requirements
            filters = self._build_pi_query_filters(protocol, scores)
            
            # Query investigators with relevant experience
            # Using embedding similarity would be ideal, but for now use filters
            query = self.supabase.table("investigators").select(
                "id, full_name, name_normalized, institution, "
                "publication_count, h_index, works_count, cited_by_count, "
                "email, phone, orcid_id"
            )
            
            # Filter by minimum publications
            min_pubs = filters.get("min_publications", 5)
            query = query.gte("publication_count", min_pubs)
            
            # Order by publication count and h-index
            query = query.order("h_index", desc=True).limit(100)
            
            result = query.execute()
            investigators = result.data if result.data else []
            
            # Score each investigator
            scored_pis = []
            for inv in investigators:
                match_score, reasons = self._calculate_pi_match_score(inv, protocol, scores)
                
                if match_score >= 50:  # Minimum threshold
                    pi_rec = PIRecommendation(
                        investigator_id=str(inv.get("id", "")),
                        full_name=inv.get("full_name", ""),
                        institution=inv.get("institution", ""),
                        match_score=match_score,
                        match_reasons=reasons,
                        experience_summary={
                            "publications": inv.get("publication_count", 0),
                            "h_index": inv.get("h_index", 0),
                            "works_count": inv.get("works_count", 0),
                            "citations": inv.get("cited_by_count", 0)
                        },
                        contact_info={
                            "email": inv.get("email"),
                            "phone": inv.get("phone"),
                            "orcid": inv.get("orcid_id")
                        } if inv.get("email") or inv.get("phone") else None
                    )
                    scored_pis.append(pi_rec)
            
            # Sort by match score and return top N
            scored_pis.sort(key=lambda x: x.match_score, reverse=True)
            return scored_pis[:limit]
            
        except Exception as e:
            print(f"Error finding matching PIs: {e}")
            return []
    
    def find_matching_pis_sync(
        self,
        protocol: ParsedProtocol,
        scores: ProtocolScores,
        limit: int = 10
    ) -> List[PIRecommendation]:
        """
        Synchronous version of find_matching_pis
        """
        import asyncio
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
        
        return loop.run_until_complete(self.find_matching_pis(protocol, scores, limit))
    
    def _generate_feasibility_summary(
        self,
        protocol: ParsedProtocol,
        scores: ProtocolScores,
        pi_count: int
    ) -> Dict[str, Any]:
        """
        Generate feasibility summary for the protocol
        """
        # Determine feasibility level
        overall = scores.overall_complexity
        if overall < 40:
            feasibility = "High"
            feasibility_description = "Protocol is straightforward with manageable complexity"
        elif overall < 60:
            feasibility = "Moderate"
            feasibility_description = "Protocol has moderate complexity requiring experienced sites"
        elif overall < 80:
            feasibility = "Challenging"
            feasibility_description = "Protocol is complex and will require careful site selection"
        else:
            feasibility = "Difficult"
            feasibility_description = "Protocol is highly complex with significant operational challenges"
        
        # Enrollment timeline estimate
        target = protocol.sample_size.target_enrollment or 100
        rate = scores.estimated_enrollment_rate
        sites_needed = max(5, int(target / (rate * 12)))  # Assuming 12-month enrollment
        
        return {
            "feasibility_level": feasibility,
            "feasibility_description": feasibility_description,
            "overall_complexity_score": scores.overall_complexity,
            "estimated_enrollment_rate_per_site_month": rate,
            "estimated_screen_fail_rate": scores.estimated_screen_fail_rate,
            "target_enrollment": target,
            "recommended_site_count": sites_needed,
            "matching_pis_found": pi_count,
            "key_challenges": self._identify_key_challenges(scores),
            "key_strengths": self._identify_key_strengths(protocol, scores)
        }
    
    def _identify_key_challenges(self, scores: ProtocolScores) -> List[str]:
        """Identify top challenges based on scores"""
        challenges = []
        
        if scores.enrollment_difficulty.score > 60:
            challenges.append("Enrollment may be challenging due to strict eligibility criteria")
        
        if scores.site_burden.score > 60:
            challenges.append("High site burden may limit site participation")
        
        if scores.amendment_risk.score > 60:
            challenges.append("Protocol amendments likely during study conduct")
        
        if scores.patient_burden.score > 60:
            challenges.append("Patient retention may be challenging due to study demands")
        
        if scores.monitoring_complexity.score > 60:
            challenges.append("Complex safety monitoring requirements")
        
        return challenges[:3]  # Top 3 challenges
    
    def _identify_key_strengths(self, protocol: ParsedProtocol, scores: ProtocolScores) -> List[str]:
        """Identify protocol strengths"""
        strengths = []
        
        if scores.enrollment_difficulty.score < 40:
            strengths.append("Broad eligibility criteria should support enrollment")
        
        if protocol.visit_schedule.telemedicine_allowed:
            strengths.append("Telemedicine options reduce patient burden")
        
        if scores.site_burden.score < 40:
            strengths.append("Manageable site burden")
        
        phase = protocol.metadata.phase.lower() if protocol.metadata.phase else ""
        if "3" in phase:
            strengths.append("Phase 3 studies typically have established procedures")
        
        if protocol.study_design.blinding == "open-label":
            strengths.append("Open-label design simplifies operations")
        
        return strengths[:3]
    
    def _generate_execution_recommendations(
        self,
        protocol: ParsedProtocol,
        scores: ProtocolScores
    ) -> List[str]:
        """
        Generate actionable execution recommendations
        """
        recommendations = []
        
        # Collect all recommendations from scores
        all_recs = (
            scores.enrollment_difficulty.recommendations +
            scores.site_burden.recommendations +
            scores.operational_complexity.recommendations +
            scores.amendment_risk.recommendations +
            scores.monitoring_complexity.recommendations +
            scores.patient_burden.recommendations
        )
        
        # Deduplicate and prioritize
        seen = set()
        for rec in all_recs:
            if rec not in seen:
                recommendations.append(rec)
                seen.add(rec)
        
        # Add protocol-specific recommendations
        if protocol.metadata.phase and "1" in protocol.metadata.phase.lower():
            recommendations.append("Ensure 24/7 medical coverage at Phase 1 sites")
        
        if protocol.sample_size.target_enrollment > 500:
            recommendations.append("Consider regional CRO support for large enrollment target")
        
        if len(protocol.sample_size.countries or []) > 3:
            recommendations.append("Plan for regulatory variations across multiple countries")
        
        return recommendations[:10]  # Top 10 recommendations
    
    def generate_recommendations(
        self,
        protocol: ParsedProtocol,
        scores: ProtocolScores,
        include_pis: bool = True,
        pi_limit: int = 10
    ) -> ProtocolRecommendations:
        """
        Generate complete recommendations for a protocol
        """
        # Find matching PIs if requested and database available
        recommended_pis = []
        if include_pis and self.supabase:
            recommended_pis = self.find_matching_pis_sync(protocol, scores, pi_limit)
        
        # Generate feasibility summary
        feasibility = self._generate_feasibility_summary(
            protocol, scores, len(recommended_pis)
        )
        
        # Generate execution recommendations
        exec_recs = self._generate_execution_recommendations(protocol, scores)
        
        return ProtocolRecommendations(
            protocol_id=protocol.metadata.protocol_number or "Unknown",
            recommended_pis=recommended_pis,
            recommended_sites=[],  # Would require site database
            feasibility_summary=feasibility,
            execution_recommendations=exec_recs
        )
