"""
Chat endpoint for conversational PI-Site recommendations.
Uses OpenAI function calling to query the database.
"""

import json
import re
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from openai import OpenAI
from api.auth import get_user_id_from_token

import os
from dotenv import load_dotenv
load_dotenv()
from src.db.supabase_client import get_supabase_admin_client
from src.recommendations.recommender import PIRecommender
from src.embeddings.generator import get_embedding

router = APIRouter()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
recommender = PIRecommender()
supabase = get_supabase_admin_client()


class ChatMessage(BaseModel):
    role: str
    content: str


class Filters(BaseModel):
    phase: Optional[str] = None
    country: Optional[str] = None


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    conversation_id: Optional[str] = None
    filters: Optional[Filters] = None


class ChatResponse(BaseModel):
    message: str
    recommendations: Optional[list[dict]] = None
    conversation_id: Optional[str] = None


# Tool definitions for function calling
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_recommendations",
            "description": "Search for PI (Principal Investigator) and clinical trial site recommendations based on a query. Use this when the user asks about finding PIs, sites, or investigators for a clinical trial.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language description of the trial, e.g., 'Phase 2 diabetes trial in the United States'"
                    },
                    "country": {
                        "type": "string",
                        "description": "Optional country filter, e.g., 'United States', 'Germany'"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 7)",
                        "default": 7
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_investigator_details",
            "description": "Get detailed information about a specific investigator/PI including their trial history and experience.",
            "parameters": {
                "type": "object",
                "properties": {
                    "investigator_id": {
                        "type": "integer",
                        "description": "The ID of the investigator"
                    },
                    "investigator_name": {
                        "type": "string",
                        "description": "The name of the investigator to search for"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_site_details",
            "description": "Get detailed information about a specific clinical trial site including location and trial history.",
            "parameters": {
                "type": "object",
                "properties": {
                    "site_id": {
                        "type": "integer",
                        "description": "The ID of the site"
                    },
                    "site_name": {
                        "type": "string",
                        "description": "The name of the site to search for"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "compare_options",
            "description": "Compare two or more PIs or sites side by side.",
            "parameters": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["investigators", "sites"],
                        "description": "What to compare: 'investigators' or 'sites'"
                    },
                    "ids": {
                        "type": "array",
                        "items": {"type": "integer"},
                        "description": "List of IDs to compare"
                    }
                },
                "required": ["type", "ids"]
            }
        }
    },
    {
        "type": "function", 
        "function": {
            "name": "search_trials",
            "description": "Search for clinical trials by keyword, condition, or other criteria.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query for trials"
                    },
                    "phase": {
                        "type": "string",
                        "description": "Trial phase filter, e.g., 'PHASE1', 'PHASE2', 'PHASE3'"
                    },
                    "status": {
                        "type": "string",
                        "description": "Trial status filter, e.g., 'RECRUITING', 'COMPLETED'"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_trial_by_nct_id",
            "description": "Get detailed information about a specific clinical trial by its NCT ID (e.g., NCT12345678). Use this when the user asks about a specific trial by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nct_id": {
                        "type": "string",
                        "description": "The NCT ID of the trial (e.g., 'NCT12345678')"
                    }
                },
                "required": ["nct_id"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_trials_by_condition",
            "description": "Search for clinical trials by medical condition. Use this when the user wants to find trials for a specific disease or condition.",
            "parameters": {
                "type": "object",
                "properties": {
                    "condition": {
                        "type": "string",
                        "description": "The medical condition to search for (e.g., 'breast cancer', 'diabetes', 'obesity')"
                    },
                    "phase": {
                        "type": "string",
                        "description": "Optional phase filter (e.g., 'PHASE2')"
                    },
                    "status": {
                        "type": "string",
                        "description": "Optional status filter (e.g., 'RECRUITING')"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum results to return",
                        "default": 10
                    }
                },
                "required": ["condition"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_pi_publications",
            "description": "Get publication and academic metrics for a Principal Investigator from Semantic Scholar data. Includes h-index, paper count, citations, and research areas.",
            "parameters": {
                "type": "object",
                "properties": {
                    "investigator_id": {
                        "type": "integer",
                        "description": "The ID of the investigator"
                    },
                    "investigator_name": {
                        "type": "string",
                        "description": "The name of the investigator to search for"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_trial_sites",
            "description": "Get all clinical trial sites for a specific trial. Use this to see where a trial is being conducted.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trial_id": {
                        "type": "integer",
                        "description": "The internal ID of the trial"
                    },
                    "nct_id": {
                        "type": "string",
                        "description": "The NCT ID of the trial (e.g., 'NCT12345678')"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_trial_investigators",
            "description": "Get all investigators/PIs working on a specific trial.",
            "parameters": {
                "type": "object",
                "properties": {
                    "trial_id": {
                        "type": "integer",
                        "description": "The internal ID of the trial"
                    },
                    "nct_id": {
                        "type": "string",
                        "description": "The NCT ID of the trial (e.g., 'NCT12345678')"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_investigator_contact",
            "description": "Get contact information (email, phone) for a Principal Investigator. Use this when the user asks for contact details, how to reach a PI, or wants to contact an investigator.",
            "parameters": {
                "type": "object",
                "properties": {
                    "investigator_id": {
                        "type": "integer",
                        "description": "The ID of the investigator"
                    },
                    "investigator_name": {
                        "type": "string",
                        "description": "The name of the investigator to search for"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_investigator_trials",
            "description": "Get ALL clinical trials for a specific investigator/PI, including NCT IDs, titles, phases, and statuses. Use this when the user asks for a list of trials an investigator has worked on, their trial history, or asks for NCT IDs.",
            "parameters": {
                "type": "object",
                "properties": {
                    "investigator_id": {
                        "type": "integer",
                        "description": "The ID of the investigator"
                    },
                    "investigator_name": {
                        "type": "string",
                        "description": "The name of the investigator to search for"
                    }
                },
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "generate_outreach_email",
            "description": "Generate a professional outreach email to a Principal Investigator for clinical trial recruitment. Use this when the user wants to draft an email, reach out to a PI, or contact an investigator about a trial opportunity.",
            "parameters": {
                "type": "object",
                "properties": {
                    "investigator_id": {
                        "type": "integer",
                        "description": "The ID of the investigator to email"
                    },
                    "investigator_name": {
                        "type": "string",
                        "description": "The name of the investigator (if ID not known)"
                    },
                    "trial_description": {
                        "type": "string",
                        "description": "Brief description of the clinical trial opportunity"
                    },
                    "therapeutic_area": {
                        "type": "string",
                        "description": "The therapeutic area (e.g., oncology, obesity, cardiology)"
                    },
                    "phase": {
                        "type": "string",
                        "description": "Trial phase (e.g., Phase 1, Phase 2, Phase 3)"
                    },
                    "sponsor_name": {
                        "type": "string",
                        "description": "Name of the sponsoring company"
                    },
                    "tone": {
                        "type": "string",
                        "enum": ["formal", "friendly", "concise"],
                        "description": "Tone of the email (default: formal)"
                    }
                },
                "required": []
            }
        }
    }
]

SYSTEM_PROMPT = """You are a clinical trial assistant that helps biotech sponsors find optimal Principal Investigators (PIs) and clinical trial sites.

You have access to a database of 577,000+ clinical trials from ClinicalTrials.gov.

AVAILABLE TOOLS:
- get_recommendations: Find PI+Site pairs for a trial query (results shown as cards)
- get_investigator_details: Get detailed info about a specific PI
- get_site_details: Get detailed info about a specific site
- compare_options: Compare multiple PIs or sites side by side
- search_trials: Search trials by keyword with vector search
- get_trial_by_nct_id: Look up a specific trial by NCT ID (fast, no embedding needed)
- get_trials_by_condition: Find trials for a specific medical condition
- get_pi_publications: Get academic metrics (h-index, papers, citations) from Semantic Scholar
- get_trial_sites: Get all sites conducting a specific trial
- get_trial_investigators: Get all PIs working on a specific trial
- get_investigator_trials: Get ALL trials for an investigator with NCT IDs (use when user asks for trial list/history)
- get_investigator_contact: Get contact info (email, phone) for a PI
- generate_outreach_email: Draft a professional outreach email to a PI about a trial opportunity

IMPORTANT: When you call get_recommendations, the results are AUTOMATICALLY displayed as visual cards in the UI. 
DO NOT repeat the recommendation details (names, sites, scores, metrics) in your text response.

Instead, your text response should:
1. Briefly acknowledge you found results (e.g., "I found X matching investigators")
2. Provide high-level insights or patterns (e.g., "Most are concentrated in the US and UK")
3. Offer to provide more details about specific PIs or sites if they want to learn more
4. Suggest follow-up actions (e.g., "Would you like me to compare the top 2?" or "I can get more details on any of these")

TOOL SELECTION GUIDE:
- User asks about a specific PI by name (e.g., "tell me about Dr. Smith") → use get_investigator_details
- User asks for a PI's trials, trial list, NCT IDs, or trial history (e.g., "what trials has X worked on", "give me all their trials", "list NCT IDs") → use get_investigator_trials
- User asks about a specific site by name → use get_site_details
- User asks about a specific NCT ID → use get_trial_by_nct_id (fast lookup)
- User asks for PI's publication/academic record → use get_pi_publications
- User asks for all sites conducting a trial → use get_trial_sites
- User asks for all investigators on a trial → use get_trial_investigators
- User wants to find NEW PIs/sites for a trial concept → use get_recommendations
- User wants to draft/write/generate an email to a PI → use generate_outreach_email (ALWAYS use this tool, don't write emails yourself)

IMPORTANT: When the user asks follow-up questions about a specific PI or site mentioned earlier, use get_investigator_details, get_investigator_trials, or get_site_details - NOT get_recommendations.

IMPORTANT: ALWAYS call a tool when the user asks a question that requires data. NEVER respond with "let me look that up" or "I'll get that for you" without actually calling a tool. If you're unsure which tool to use, default to get_investigator_details for PI questions or search_trials for trial questions.

IMPORTANT: When the user asks to draft, write, or generate an email to contact a PI, ALWAYS use the generate_outreach_email tool. Do NOT write the email yourself in your response.

IMPORTANT: When you receive results from generate_outreach_email, ALWAYS display the FULL email content including:
- To: (email address)
- Subject: (subject line)
- Body: (complete email text)
Format it as plain text WITHOUT code blocks or dark backgrounds. Do NOT use ``` formatting. Just display the email content directly so the user can easily read and copy it.

Keep responses concise - the cards already show the key data.
"""


def execute_tool(tool_name: str, arguments: dict, filters: Optional[Filters] = None) -> dict:
    """Execute a tool function and return the result."""
    
    if tool_name == "get_recommendations":
        # Use filters from request if not specified in arguments
        country = arguments.get("country") or (filters.country if filters else None)
        phase = arguments.get("phase") or (filters.phase if filters else None)
        
        results = recommender.recommend(
            query=arguments["query"],
            country=country,
            phase=phase,
            max_results=arguments.get("max_results", 7)
        )
        return {
            "recommendations": results,
            "count": len(results),
            "query": arguments["query"],
            "filters_applied": {"country": country, "phase": phase}
        }
    
    elif tool_name == "get_investigator_details":
        inv_id = arguments.get("investigator_id")
        inv_name = arguments.get("investigator_name")
        
        if inv_id:
            result = supabase.table("investigators").select("*").eq("id", inv_id).execute()
        elif inv_name:
            result = supabase.table("investigators").select("*").ilike("full_name", f"%{inv_name}%").limit(5).execute()
        else:
            return {"error": "Please provide either investigator_id or investigator_name"}
        
        if not result.data:
            return {"error": "Investigator not found"}
        
        # Helper function to enrich a single investigator
        def enrich_investigator(inv_data):
            the_id = inv_data["id"]
            
            def get_trial_count():
                return supabase.table("trial_investigators").select("trial_id", count="exact").eq("investigator_id", the_id).limit(1).execute()
            
            def get_recent_trials():
                trial_inv = supabase.table("trial_investigators").select(
                    "trial_id, role, trials(nct_id, brief_title, phase, overall_status, conditions)"
                ).eq("investigator_id", the_id).limit(10).execute()
                return trial_inv
            
            def get_sites():
                sites = supabase.table("investigator_sites").select(
                    "site_id, link_type, sites(facility_name, city, country)"
                ).eq("investigator_id", the_id).limit(5).execute()
                return sites
            
            with ThreadPoolExecutor(max_workers=3) as executor:
                count_future = executor.submit(get_trial_count)
                trials_future = executor.submit(get_recent_trials)
                sites_future = executor.submit(get_sites)
                
                trial_count = count_future.result()
                recent_trials = trials_future.result()
                sites = sites_future.result()
            
            inv_data["trial_count"] = trial_count.count or 0
            inv_data["recent_trials"] = [t.get("trials") for t in recent_trials.data if t.get("trials")] if recent_trials.data else []
            inv_data["sites"] = [s.get("sites") for s in sites.data if s.get("sites")] if sites.data else []
            return inv_data
        
        if inv_id:
            # Single investigator by ID - enrich it
            inv = enrich_investigator(result.data[0])
            return {"investigator": inv}
        else:
            # Multiple matches by name - enrich the first/best match only for performance
            # but return all matches so user can see options
            if len(result.data) == 1:
                inv = enrich_investigator(result.data[0])
                return {"investigator": inv}
            else:
                # Enrich the first match, return others as basic info
                enriched = enrich_investigator(result.data[0])
                others = result.data[1:]
                return {
                    "investigator": enriched,
                    "other_matches": others,
                    "message": f"Found {len(result.data)} investigators matching '{inv_name}'. Showing details for the first match."
                }
    
    elif tool_name == "get_site_details":
        site_id = arguments.get("site_id")
        site_name = arguments.get("site_name")
        
        if site_id:
            result = supabase.table("sites").select("*").eq("id", site_id).execute()
        elif site_name:
            result = supabase.table("sites").select("*").ilike("facility_name", f"%{site_name}%").limit(5).execute()
        else:
            return {"error": "Please provide either site_id or site_name"}
        
        if not result.data:
            return {"error": "Site not found"}
        
        # Helper function to enrich a single site
        def enrich_site(site_data):
            the_id = site_data["id"]
            
            def get_trial_count():
                return supabase.table("trial_sites").select("trial_id", count="exact").eq("site_id", the_id).limit(1).execute()
            
            def get_recent_trials():
                trial_sites = supabase.table("trial_sites").select(
                    "trial_id, trials(nct_id, brief_title, phase, overall_status, conditions)"
                ).eq("site_id", the_id).limit(10).execute()
                return trial_sites
            
            def get_investigators():
                invs = supabase.table("investigator_sites").select(
                    "investigator_id, link_type, investigators(full_name)"
                ).eq("site_id", the_id).limit(10).execute()
                return invs
            
            with ThreadPoolExecutor(max_workers=3) as executor:
                count_future = executor.submit(get_trial_count)
                trials_future = executor.submit(get_recent_trials)
                invs_future = executor.submit(get_investigators)
                
                trial_count = count_future.result()
                recent_trials = trials_future.result()
                investigators = invs_future.result()
            
            site_data["trial_count"] = trial_count.count or 0
            site_data["recent_trials"] = [t.get("trials") for t in recent_trials.data if t.get("trials")] if recent_trials.data else []
            site_data["investigators"] = [i.get("investigators") for i in investigators.data if i.get("investigators")] if investigators.data else []
            return site_data
        
        if site_id:
            site = enrich_site(result.data[0])
            return {"site": site}
        else:
            if len(result.data) == 1:
                site = enrich_site(result.data[0])
                return {"site": site}
            else:
                enriched = enrich_site(result.data[0])
                others = result.data[1:]
                return {
                    "site": enriched,
                    "other_matches": others,
                    "message": f"Found {len(result.data)} sites matching '{site_name}'. Showing details for the first match."
                }
    
    elif tool_name == "compare_options":
        compare_type = arguments["type"]
        ids = arguments["ids"]
        
        if compare_type == "investigators":
            result = supabase.table("investigators").select("*").in_("id", ids).execute()
            items = result.data
            
            # Batch fetch trial counts using parallel queries (faster than sequential)
            def get_trial_count(inv_id):
                try:
                    r = supabase.table("trial_investigators").select("trial_id", count="exact").eq("investigator_id", inv_id).limit(1).execute()
                    return inv_id, r.count or 0
                except:
                    return inv_id, 0
            
            with ThreadPoolExecutor(max_workers=len(ids)) as executor:
                counts = dict(executor.map(lambda i: get_trial_count(i), ids))
            
            for item in items:
                item["trial_count"] = counts.get(item["id"], 0)
            
            return {"investigators": items}
        
        elif compare_type == "sites":
            result = supabase.table("sites").select("*").in_("id", ids).execute()
            
            # Batch fetch trial counts for sites
            def get_site_trial_count(site_id):
                try:
                    r = supabase.table("trial_sites").select("trial_id", count="exact").eq("site_id", site_id).limit(1).execute()
                    return site_id, r.count or 0
                except:
                    return site_id, 0
            
            with ThreadPoolExecutor(max_workers=len(ids)) as executor:
                counts = dict(executor.map(lambda i: get_site_trial_count(i), ids))
            
            for site in result.data:
                site["trial_count"] = counts.get(site["id"], 0)
            
            return {"sites": result.data}
        
        return {"error": "Invalid comparison type"}
    
    elif tool_name == "search_trials":
        query = arguments["query"]
        limit = arguments.get("limit", 10)
        phase = arguments.get("phase")
        status = arguments.get("status")
        
        # Check if query is an NCT ID (exact lookup)
        nct_pattern = r'^NCT\d{8}$'
        if re.match(nct_pattern, query.upper()):
            result = supabase.table("trials").select(
                "id, nct_id, brief_title, phase, overall_status, conditions, enrollment, start_date, lead_sponsor_name"
            ).eq("nct_id", query.upper()).execute()
            return {"trials": result.data, "count": len(result.data), "search_type": "nct_id"}
        
        # Use vector search for semantic matching
        try:
            query_embedding = get_embedding(query)
            result = supabase.rpc("search_trials_by_embedding", {
                "query_embedding": query_embedding,
                "similarity_threshold": 0.4,
                "max_results": limit
            }).execute()
            
            if result.data:
                # Get full trial details for the matched IDs
                trial_ids = [r["id"] for r in result.data]
                trials = supabase.table("trials").select(
                    "id, nct_id, brief_title, phase, overall_status, conditions, enrollment"
                ).in_("id", trial_ids).execute()
                
                # Apply optional filters
                filtered = trials.data
                if phase:
                    filtered = [t for t in filtered if t.get("phase") == phase]
                if status:
                    filtered = [t for t in filtered if t.get("overall_status") == status]
                
                return {"trials": filtered[:limit], "count": len(filtered), "search_type": "vector"}
        except Exception as e:
            print(f"Vector search failed: {e}, falling back to text search")
        
        # Fallback to ILIKE text search
        query_builder = supabase.table("trials").select(
            "id, nct_id, brief_title, phase, overall_status, conditions"
        ).eq("avoid_search", False).ilike("brief_title", f"%{query}%")
        
        if phase:
            query_builder = query_builder.eq("phase", phase)
        if status:
            query_builder = query_builder.eq("overall_status", status)
        
        result = query_builder.limit(limit).execute()
        return {"trials": result.data, "count": len(result.data), "search_type": "text"}
    
    elif tool_name == "get_trial_by_nct_id":
        nct_id = arguments["nct_id"].upper()
        
        # Get full trial details
        result = supabase.table("trials").select(
            "id, nct_id, brief_title, official_title, phase, overall_status, conditions, "
            "enrollment, start_date, completion_date, lead_sponsor_name, brief_summary, study_type"
        ).eq("nct_id", nct_id).execute()
        
        if not result.data:
            return {"error": f"Trial {nct_id} not found"}
        
        trial = result.data[0]
        
        # Get site and investigator counts in parallel
        def get_site_count():
            return supabase.table("trial_sites").select("site_id", count="exact").eq("trial_id", trial["id"]).limit(1).execute()
        
        def get_inv_count():
            return supabase.table("trial_investigators").select("investigator_id", count="exact").eq("trial_id", trial["id"]).limit(1).execute()
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            site_future = executor.submit(get_site_count)
            inv_future = executor.submit(get_inv_count)
            
            site_count = site_future.result()
            inv_count = inv_future.result()
        
        trial["site_count"] = site_count.count or 0
        trial["investigator_count"] = inv_count.count or 0
        
        return {"trial": trial}
    
    elif tool_name == "get_trials_by_condition":
        condition = arguments["condition"]
        limit = arguments.get("limit", 10)
        phase = arguments.get("phase")
        status = arguments.get("status")
        
        # Search in conditions array using contains (exclude avoid_search trials)
        query_builder = supabase.table("trials").select(
            "id, nct_id, brief_title, phase, overall_status, conditions, enrollment, start_date"
        ).eq("avoid_search", False).contains("conditions", [condition])
        
        if phase:
            query_builder = query_builder.eq("phase", phase)
        if status:
            query_builder = query_builder.eq("overall_status", status)
        
        result = query_builder.limit(limit).execute()
        
        # If exact match fails, try ILIKE on conditions array (cast to text)
        if not result.data:
            result = supabase.table("trials").select(
                "id, nct_id, brief_title, phase, overall_status, conditions, enrollment, start_date"
            ).eq("avoid_search", False).ilike("brief_title", f"%{condition}%").limit(limit).execute()
        
        return {"trials": result.data, "count": len(result.data), "condition": condition}
    
    elif tool_name == "get_pi_publications":
        inv_id = arguments.get("investigator_id")
        inv_name = arguments.get("investigator_name")
        
        # Try to get Semantic Scholar columns if they exist
        try:
            if inv_id:
                result = supabase.table("investigators").select(
                    "id, full_name, affiliation, semantic_scholar_id, h_index, paper_count, "
                    "citation_count, research_areas, notable_papers, s2_match_confidence"
                ).eq("id", inv_id).execute()
            elif inv_name:
                result = supabase.table("investigators").select(
                    "id, full_name, affiliation, semantic_scholar_id, h_index, paper_count, "
                    "citation_count, research_areas, notable_papers, s2_match_confidence"
                ).ilike("full_name", f"%{inv_name}%").limit(5).execute()
            else:
                return {"error": "Please provide either investigator_id or investigator_name"}
        except Exception:
            # Semantic Scholar columns don't exist yet, fall back to basic info
            if inv_id:
                result = supabase.table("investigators").select(
                    "id, full_name, affiliation"
                ).eq("id", inv_id).execute()
            elif inv_name:
                result = supabase.table("investigators").select(
                    "id, full_name, affiliation"
                ).ilike("full_name", f"%{inv_name}%").limit(5).execute()
            else:
                return {"error": "Please provide either investigator_id or investigator_name"}
            
            if not result.data:
                return {"error": "Investigator not found"}
            
            return {
                "investigator": result.data[0] if inv_id else result.data,
                "has_publications": False,
                "message": "Semantic Scholar enrichment not yet available. Run the enrichment script to add publication data."
            }
        
        if not result.data:
            return {"error": "Investigator not found"}
        
        inv = result.data[0] if inv_id else result.data
        
        # Check if we have Semantic Scholar data
        if isinstance(inv, dict) and not inv.get("h_index"):
            return {
                "investigator": inv,
                "has_publications": False,
                "message": "No Semantic Scholar data available for this investigator"
            }
        
        return {"investigator": inv, "has_publications": True}
    
    elif tool_name == "get_trial_sites":
        trial_id = arguments.get("trial_id")
        nct_id = arguments.get("nct_id")
        
        # Get trial_id from nct_id if needed
        if nct_id and not trial_id:
            trial_result = supabase.table("trials").select("id").eq("nct_id", nct_id.upper()).execute()
            if not trial_result.data:
                return {"error": f"Trial {nct_id} not found"}
            trial_id = trial_result.data[0]["id"]
        
        if not trial_id:
            return {"error": "Please provide either trial_id or nct_id"}
        
        # Get all sites for this trial
        result = supabase.table("trial_sites").select(
            "site_id, recruitment_status, sites(id, facility_name, city, state, country, zip)"
        ).eq("trial_id", trial_id).execute()
        
        sites = [
            {**r.get("sites", {}), "recruitment_status": r.get("recruitment_status")}
            for r in result.data if r.get("sites")
        ]
        
        return {"sites": sites, "count": len(sites), "trial_id": trial_id}
    
    elif tool_name == "get_trial_investigators":
        trial_id = arguments.get("trial_id")
        nct_id = arguments.get("nct_id")
        
        # Get trial_id from nct_id if needed
        if nct_id and not trial_id:
            trial_result = supabase.table("trials").select("id").eq("nct_id", nct_id.upper()).execute()
            if not trial_result.data:
                return {"error": f"Trial {nct_id} not found"}
            trial_id = trial_result.data[0]["id"]
        
        if not trial_id:
            return {"error": "Please provide either trial_id or nct_id"}
        
        # Get all investigators for this trial
        result = supabase.table("trial_investigators").select(
            "investigator_id, role, investigators(id, full_name, affiliation)"
        ).eq("trial_id", trial_id).execute()
        
        investigators = [
            {**r.get("investigators", {}), "role": r.get("role")}
            for r in result.data if r.get("investigators")
        ]
        
        return {"investigators": investigators, "count": len(investigators), "trial_id": trial_id}
    
    elif tool_name == "get_investigator_contact":
        inv_id = arguments.get("investigator_id")
        inv_name = arguments.get("investigator_name")
        
        if inv_id:
            result = supabase.table("investigators").select(
                "id,full_name,affiliation,email,phone"
            ).eq("id", inv_id).execute()
        elif inv_name:
            # Clean up name - remove common prefixes
            clean_name = inv_name.replace("Dr. ", "").replace("Dr ", "").replace("Prof. ", "").replace("Prof ", "").strip()
            result = supabase.table("investigators").select(
                "id,full_name,affiliation,email,phone"
            ).ilike("full_name", f"%{clean_name}%").limit(10).execute()
        else:
            return {"error": "Please provide either investigator_id or investigator_name"}
        
        if not result.data:
            return {"error": "Investigator not found"}
        
        # Deduplicate by name - keep the one with contact info if available
        if inv_id:
            inv = result.data[0]
        else:
            # Normalize name for deduplication (remove titles, suffixes, extra spaces)
            def normalize_name(name: str) -> str:
                import re
                n = name.lower().strip()
                # Remove common titles and suffixes
                for suffix in [", md", ", phd", ", do", " md", " phd", " do", ", m.d.", ", ph.d."]:
                    n = n.replace(suffix, "")
                # Remove extra whitespace
                n = re.sub(r'\s+', ' ', n).strip()
                return n
            
            # Group by normalized name, prefer entries with contact info
            seen_names = {}
            for r in result.data:
                name_key = normalize_name(r.get("full_name", ""))
                has_contact = bool(r.get("email") or r.get("phone"))
                
                if name_key not in seen_names:
                    seen_names[name_key] = r
                elif has_contact and not (seen_names[name_key].get("email") or seen_names[name_key].get("phone")):
                    # Replace with this one since it has contact info
                    seen_names[name_key] = r
            
            unique_investigators = list(seen_names.values())
            
            if len(unique_investigators) == 1:
                inv = unique_investigators[0]
            else:
                # Multiple unique matches
                return {
                    "investigators": unique_investigators,
                    "count": len(unique_investigators),
                    "message": f"Found {len(unique_investigators)} investigators matching '{inv_name}'. Showing contact info for all matches."
                }
        
        # Single investigator result
        has_contact = bool(inv.get("email") or inv.get("phone"))
        return {
            "investigator": inv,
            "has_contact_info": has_contact,
            "message": "Contact information available" if has_contact else "No contact information on file for this investigator. Contact info is only available for site-level contacts listed in ClinicalTrials.gov."
        }
    
    elif tool_name == "get_investigator_trials":
        inv_id = arguments.get("investigator_id")
        inv_name = arguments.get("investigator_name")
        
        # Resolve investigator ID from name if needed
        if not inv_id and inv_name:
            clean_name = inv_name.replace("Dr. ", "").replace("Dr ", "").replace("Prof. ", "").replace("Prof ", "").strip()
            inv_result = supabase.table("investigators").select("id, full_name").ilike("full_name", f"%{clean_name}%").limit(1).execute()
            if inv_result.data:
                inv_id = inv_result.data[0]["id"]
                inv_name = inv_result.data[0]["full_name"]
            else:
                return {"error": f"Investigator '{inv_name}' not found"}
        
        if not inv_id:
            return {"error": "Please provide either investigator_id or investigator_name"}
        
        # Get ALL trials for this investigator (no limit)
        trial_inv = supabase.table("trial_investigators").select(
            "trial_id, role, trials(nct_id, brief_title, phase, overall_status, conditions, start_date)"
        ).eq("investigator_id", inv_id).execute()
        
        trials = []
        for t in trial_inv.data or []:
            trial_data = t.get("trials")
            if trial_data:
                trial_data["role"] = t.get("role")
                trials.append(trial_data)
        
        return {
            "investigator_name": inv_name,
            "investigator_id": inv_id,
            "total_trials": len(trials),
            "trials": trials
        }
    
    elif tool_name == "generate_outreach_email":
        inv_id = arguments.get("investigator_id")
        inv_name = arguments.get("investigator_name")
        trial_desc = arguments.get("trial_description", "a clinical trial opportunity")
        therapeutic_area = arguments.get("therapeutic_area", "")
        phase = arguments.get("phase", "")
        sponsor_name = arguments.get("sponsor_name", "our company")
        tone = arguments.get("tone", "formal")
        
        # Get investigator details
        inv_data = None
        if inv_id:
            result = supabase.table("investigators").select(
                "id,full_name,affiliation,email,phone"
            ).eq("id", inv_id).execute()
            if result.data:
                inv_data = result.data[0]
        elif inv_name:
            # Clean up name - remove common prefixes
            clean_name = inv_name.replace("Dr. ", "").replace("Dr ", "").replace("Prof. ", "").replace("Prof ", "").strip()
            result = supabase.table("investigators").select(
                "id,full_name,affiliation,email,phone"
            ).ilike("full_name", f"%{clean_name}%").limit(1).execute()
            if result.data:
                inv_data = result.data[0]
        
        if not inv_data:
            return {"error": "Investigator not found. Please provide a valid investigator ID or name."}
        
        # Build context for email generation
        pi_name = inv_data.get("full_name", "Dr.")
        pi_affiliation = inv_data.get("affiliation", "your institution")
        pi_email = inv_data.get("email")
        pub_count = inv_data.get("publication_count") or 0
        h_index = inv_data.get("h_index") or 0
        
        # Generate email using OpenAI
        email_prompt = f"""Generate a professional outreach email to recruit a Principal Investigator for a clinical trial.

PI Details:
- Name: {pi_name}
- Institution: {pi_affiliation}
- Publications: {pub_count}, H-index: {h_index}

Trial Details:
- Description: {trial_desc}
- Therapeutic Area: {therapeutic_area or 'Not specified'}
- Phase: {phase or 'Not specified'}
- Sponsor: {sponsor_name}

Tone: {tone}

Requirements:
1. Address the PI by name
2. Reference their expertise/institution if relevant
3. Briefly describe the trial opportunity
4. Highlight why they would be a good fit
5. Include a clear call to action
6. Keep it concise (under 200 words)
7. Do NOT include placeholder brackets like [Your Name] - leave signature area blank

Generate ONLY the email body, starting with the greeting."""

        email_response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": email_prompt}],
            temperature=0.7,
            max_tokens=500
        )
        
        email_body = email_response.choices[0].message.content
        
        return {
            "email": {
                "to": pi_email or f"[{pi_name}'s email not on file]",
                "to_name": pi_name,
                "subject": f"Clinical Trial Opportunity: {therapeutic_area or 'Research'} {phase or 'Study'}",
                "body": email_body
            },
            "investigator": {
                "id": inv_data.get("id"),
                "name": pi_name,
                "affiliation": pi_affiliation,
                "email": pi_email
            },
            "message": f"Generated outreach email for {pi_name}" + (f" ({pi_email})" if pi_email else " - note: email address not on file")
        }
    
    return {"error": f"Unknown tool: {tool_name}"}


def is_search_query(message: str) -> bool:
    """Detect if message is a simple search query (skip LLM tool-calling)."""
    lower = message.lower()
    
    # Keywords that indicate NOT a simple search (need LLM reasoning)
    # Use word boundaries to avoid "show" matching "how"
    complex_patterns = [
        r'\bcompare\b', r'\bdifference\b', r'\btell me about\b', r'\bdetails\b', 
        r'\bexplain\b', r'\bwhy\b', r'\bhow\b', r'\bwhat is\b', r'\bwho is\b', 
        r'\bmore info\b', r'\bspecific\b', r'\bwhich one\b', r'\bbetter\b', 
        r'\bversus\b', r'\bvs\b',
        r'\bemail\b', r'\bdraft\b', r'\bwrite\b', r'\boutreach\b', r'\bcontact\b'
    ]
    
    # If it's a complex query, use full LLM flow
    if any(re.search(p, lower) for p in complex_patterns):
        return False
    
    # Keywords that indicate SEARCH INTENT (action words)
    search_intent_keywords = [
        'find', 'search', 'looking for', 'recommend', 'get', 'show me',
        'investigators for', 'pis for', 'sites for', 'list', 'give me'
    ]
    
    # If explicit search intent, use fast path
    if any(kw in lower for kw in search_intent_keywords):
        return True
    
    # Pattern: "[condition] trial" or "phase [n] [condition]" → likely a search
    trial_pattern = r'\b(trial|study|trials|studies)\b'
    phase_pattern = r'\bphase\s*[1-4i]+\b'
    
    if re.search(trial_pattern, lower) or re.search(phase_pattern, lower):
        return True
    
    return False


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Process a chat message and return a response with optional recommendations.
    """
    try:
        last_message = request.messages[-1].content if request.messages else ""
        
        # Optimization: For simple search queries, skip the first LLM call
        # and directly call the recommender, then use 1 LLM call for response
        if is_search_query(last_message) and len(request.messages) == 1:
            # Direct search path - skip tool-calling LLM call
            result = execute_tool("get_recommendations", {"query": last_message}, request.filters)
            recommendations = result.get("recommendations", [])
            
            # Single LLM call to generate response based on results
            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": last_message},
                {"role": "assistant", "content": None, "tool_calls": [{
                    "id": "direct_search",
                    "type": "function", 
                    "function": {"name": "get_recommendations", "arguments": json.dumps({"query": last_message})}
                }]},
                {"role": "tool", "tool_call_id": "direct_search", "content": json.dumps(result)}
            ]
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            
            return ChatResponse(
                message=response.choices[0].message.content,
                recommendations=recommendations,
                conversation_id=request.conversation_id
            )
        
        # Standard path: Use LLM with tools for complex queries or follow-ups
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        
        for msg in request.messages:
            messages.append({"role": msg.role, "content": msg.content})
        
        # Call OpenAI with tools
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            tools=TOOLS,
            tool_choice="auto"
        )
        
        assistant_message = response.choices[0].message
        recommendations = None
        
        # Handle tool calls
        if assistant_message.tool_calls:
            # Execute tool calls in PARALLEL for better latency
            def execute_single_tool(tool_call):
                tool_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                result = execute_tool(tool_name, arguments, request.filters)
                return tool_call.id, result
            
            tool_results = []
            with ThreadPoolExecutor(max_workers=len(assistant_message.tool_calls)) as executor:
                futures = {executor.submit(execute_single_tool, tc): tc for tc in assistant_message.tool_calls}
                for future in as_completed(futures):
                    tool_call_id, result = future.result()
                    tool_results.append({
                        "tool_call_id": tool_call_id,
                        "role": "tool",
                        "content": json.dumps(result)
                    })
                    
                    # Extract recommendations if present
                    if "recommendations" in result:
                        recommendations = result["recommendations"]
            
            # Add assistant message and tool results to conversation
            messages.append({
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments
                        }
                    }
                    for tc in assistant_message.tool_calls
                ]
            })
            messages.extend(tool_results)
            
            # Get final response from model
            final_response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages
            )
            
            final_content = final_response.choices[0].message.content
        else:
            final_content = assistant_message.content
        
        return ChatResponse(
            message=final_content,
            recommendations=recommendations,
            conversation_id=request.conversation_id
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    Stream chat responses for better UX.
    """
    async def generate():
        try:
            messages = [{"role": "system", "content": SYSTEM_PROMPT}]
            for msg in request.messages:
                messages.append({"role": msg.role, "content": msg.content})
            
            # First call to check for tool use
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                tools=TOOLS,
                tool_choice="auto"
            )
            
            assistant_message = response.choices[0].message
            
            # Handle tool calls
            if assistant_message.tool_calls:
                recommendations = None
                tool_results = []
                
                # Execute tool calls in PARALLEL for better latency
                def execute_single_tool(tool_call):
                    tool_name = tool_call.function.name
                    arguments = json.loads(tool_call.function.arguments)
                    result = execute_tool(tool_name, arguments, request.filters)
                    return tool_call.id, result
                
                with ThreadPoolExecutor(max_workers=len(assistant_message.tool_calls)) as executor:
                    futures = {executor.submit(execute_single_tool, tc): tc for tc in assistant_message.tool_calls}
                    for future in as_completed(futures):
                        tool_call_id, result = future.result()
                        tool_results.append({
                            "tool_call_id": tool_call_id,
                            "role": "tool", 
                            "content": json.dumps(result)
                        })
                        
                        if "recommendations" in result:
                            recommendations = result["recommendations"]
                            # Send recommendations immediately
                            yield f"data: {json.dumps({'type': 'recommendations', 'data': recommendations})}\n\n"
                
                # Build messages for final response
                messages.append({
                    "role": "assistant",
                    "content": assistant_message.content or "",
                    "tool_calls": [
                        {
                            "id": tc.id,
                            "type": "function",
                            "function": {
                                "name": tc.function.name,
                                "arguments": tc.function.arguments
                            }
                        }
                        for tc in assistant_message.tool_calls
                    ]
                })
                messages.extend(tool_results)
                
                # Stream final response
                stream = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    stream=True
                )
                
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        yield f"data: {json.dumps({'type': 'content', 'data': chunk.choices[0].delta.content})}\n\n"
            else:
                # No tool calls, stream directly
                stream = client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=messages,
                    stream=True
                )
                
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        yield f"data: {json.dumps({'type': 'content', 'data': chunk.choices[0].delta.content})}\n\n"
            
            yield f"data: {json.dumps({'type': 'done'})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'data': str(e)})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        }
    )


# Conversation persistence endpoints (require database tables)
def check_tables_exist():
    """Check if chat tables exist in database."""
    try:
        supabase.table("conversations").select("id").limit(1).execute()
        return True
    except Exception:
        return False


@router.get("/conversations")
async def list_conversations(user_id: str = Depends(get_user_id_from_token)):
    """List all conversations for the authenticated user."""
    if not check_tables_exist():
        raise HTTPException(status_code=503, detail="Database tables not created yet")
    
    try:
        query = supabase.table("conversations").select(
            "id, title, created_at, updated_at"
        ).order("updated_at", desc=True).limit(50)
        
        # Filter by user_id if authenticated
        if user_id:
            query = query.eq("user_id", user_id)
        
        result = query.execute()
        return {"conversations": result.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/conversations/{conversation_id}")
async def get_conversation(conversation_id: str, user_id: str = Depends(get_user_id_from_token)):
    """Get a conversation with all its messages."""
    if not check_tables_exist():
        raise HTTPException(status_code=503, detail="Database tables not created yet")
    
    try:
        # Get conversation (with user_id check if authenticated)
        query = supabase.table("conversations").select("*").eq("id", conversation_id)
        if user_id:
            query = query.eq("user_id", user_id)
        conv = query.single().execute()
        
        # Get messages
        messages = supabase.table("messages").select("*").eq(
            "conversation_id", conversation_id
        ).order("created_at").execute()
        
        return {
            "conversation": conv.data,
            "messages": messages.data
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class SaveConversationRequest(BaseModel):
    title: str
    messages: list[dict]


@router.post("/conversations")
async def save_conversation(request: SaveConversationRequest, user_id: str = Depends(get_user_id_from_token)):
    """Save a new conversation."""
    if not check_tables_exist():
        raise HTTPException(status_code=503, detail="Database tables not created yet")
    
    try:
        # Create conversation with user_id if authenticated
        conv_data = {"title": request.title}
        if user_id:
            conv_data["user_id"] = user_id
        conv = supabase.table("conversations").insert(conv_data).execute()
        
        conversation_id = conv.data[0]["id"]
        
        # Insert messages
        for msg in request.messages:
            supabase.table("messages").insert({
                "conversation_id": conversation_id,
                "role": msg.get("role"),
                "content": msg.get("content"),
                "metadata": msg.get("metadata", {})
            }).execute()
        
        return {"conversation_id": conversation_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class AppendMessagesRequest(BaseModel):
    messages: list[dict]


@router.post("/conversations/{conversation_id}/messages")
async def append_messages(conversation_id: str, request: AppendMessagesRequest, user_id: str = Depends(get_user_id_from_token)):
    """Append new messages to an existing conversation."""
    if not check_tables_exist():
        raise HTTPException(status_code=503, detail="Database tables not created yet")
    
    try:
        # Verify conversation exists and belongs to user
        query = supabase.table("conversations").select("id").eq("id", conversation_id)
        if user_id:
            query = query.eq("user_id", user_id)
        conv = query.limit(1).execute()
        if not conv.data:
            raise HTTPException(status_code=404, detail="Conversation not found")
        
        # Insert new messages
        for msg in request.messages:
            supabase.table("messages").insert({
                "conversation_id": conversation_id,
                "role": msg.get("role"),
                "content": msg.get("content"),
                "metadata": msg.get("metadata", {})
            }).execute()
        
        return {"appended": len(request.messages)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/conversations/{conversation_id}")
async def delete_conversation(conversation_id: str, user_id: str = Depends(get_user_id_from_token)):
    """Delete a conversation and its messages."""
    if not check_tables_exist():
        raise HTTPException(status_code=503, detail="Database tables not created yet")
    
    try:
        query = supabase.table("conversations").delete().eq("id", conversation_id)
        if user_id:
            query = query.eq("user_id", user_id)
        query.execute()
        return {"deleted": True}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
