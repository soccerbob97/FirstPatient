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
                        "description": "Maximum number of results to return (default 10)",
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
    }
]

SYSTEM_PROMPT = """You are a clinical trial assistant that helps biotech sponsors find optimal Principal Investigators (PIs) and clinical trial sites.

You have access to a database of 577,000+ clinical trials from ClinicalTrials.gov.

IMPORTANT: When you call get_recommendations, the results are AUTOMATICALLY displayed as visual cards in the UI. 
DO NOT repeat the recommendation details (names, sites, scores, metrics) in your text response.

Instead, your text response should:
1. Briefly acknowledge you found results (e.g., "I found X matching investigators")
2. Provide high-level insights or patterns (e.g., "Most are concentrated in the US and UK")
3. Offer to provide more details about specific PIs or sites if they want to learn more
4. Suggest follow-up actions (e.g., "Would you like me to compare the top 2?" or "I can get more details on any of these")

When users ask follow-up questions about specific investigators or sites mentioned in the cards, use get_investigator_details or get_site_details to provide additional context not shown in the cards.

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
            max_results=arguments.get("max_results", 10)
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
        
        inv = result.data[0] if inv_id else result.data
        
        # Get enriched data in parallel
        if inv_id or (isinstance(inv, dict) and inv.get("id")):
            the_id = inv_id or inv["id"]
            
            def get_trial_count():
                return supabase.table("trial_investigators").select("trial_id", count="exact").eq("investigator_id", the_id).limit(1).execute()
            
            def get_recent_trials():
                # Get recent trial details for this investigator
                trial_inv = supabase.table("trial_investigators").select(
                    "trial_id, role, trials(nct_id, brief_title, phase, overall_status, conditions)"
                ).eq("investigator_id", the_id).limit(10).execute()
                return trial_inv
            
            def get_sites():
                # Get sites this investigator has worked at
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
            
            if isinstance(inv, dict):
                inv["trial_count"] = trial_count.count or 0
                inv["recent_trials"] = [t.get("trials") for t in recent_trials.data if t.get("trials")] if recent_trials.data else []
                inv["sites"] = [s.get("sites") for s in sites.data if s.get("sites")] if sites.data else []
        
        return {"investigator": inv}
    
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
        
        site = result.data[0] if site_id else result.data
        
        # Get enriched data in parallel
        if site_id or (isinstance(site, dict) and site.get("id")):
            the_id = site_id or site["id"]
            
            def get_trial_count():
                return supabase.table("trial_sites").select("trial_id", count="exact").eq("site_id", the_id).limit(1).execute()
            
            def get_recent_trials():
                trial_sites = supabase.table("trial_sites").select(
                    "trial_id, trials(nct_id, brief_title, phase, overall_status, conditions)"
                ).eq("site_id", the_id).limit(10).execute()
                return trial_sites
            
            def get_investigators():
                # Get investigators who have worked at this site
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
            
            if isinstance(site, dict):
                site["trial_count"] = trial_count.count or 0
                site["recent_trials"] = [t.get("trials") for t in recent_trials.data if t.get("trials")] if recent_trials.data else []
                site["investigators"] = [i.get("investigators") for i in investigators.data if i.get("investigators")] if investigators.data else []
        
        return {"site": site}
    
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
                "id, nct_id, brief_title, phase, overall_status, conditions, enrollment, start_date, sponsor"
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
        ).ilike("brief_title", f"%{query}%")
        
        if phase:
            query_builder = query_builder.eq("phase", phase)
        if status:
            query_builder = query_builder.eq("overall_status", status)
        
        result = query_builder.limit(limit).execute()
        return {"trials": result.data, "count": len(result.data), "search_type": "text"}
    
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
        r'\bversus\b', r'\bvs\b'
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
