#!/usr/bin/env python3
"""
Step 7: Compare Embedding Models

Tests multiple embedding models on a sample of trials and compares search quality.
Helps decide which model to use for production.

Models tested:
- Voyage 3.5-lite (1024d) - Current plan
- Voyage 4 (1024d) - Newest, best value
- OpenAI text-embedding-3-small (1536d) - Current production
- Gemini Embedding 2 (1536d) - Best accuracy (optional)

Requirements:
    - VOYAGE_API_KEY in .env
    - OPENAI_API_KEY in .env
    - GOOGLE_API_KEY in .env (optional, for Gemini)
    - pip install voyageai openai google-generativeai

Usage:
    PYTHONPATH=. python scripts/v2_test/07_compare_embedding_models.py
    PYTHONPATH=. python scripts/v2_test/07_compare_embedding_models.py --sample-size 50
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path
from datetime import datetime
from typing import Optional
import numpy as np

from dotenv import load_dotenv

load_dotenv()

DATA_DIR = Path(__file__).parent / "data"

# Direct Supabase connection (avoid local supabase/ folder shadowing)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_KEY") or os.getenv("SUPABASE_KEY")


class SimpleSupabaseClient:
    """Simple Supabase client using requests to avoid import issues."""
    
    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
    
    def query(self, table: str, select: str = "*", filters: dict = None, limit: int = None) -> list[dict]:
        """Query a table."""
        import requests
        
        url = f"{self.url}/rest/v1/{table}?select={select}"
        
        if filters:
            for key, value in filters.items():
                if isinstance(value, list):
                    url += f"&{key}=in.({','.join(map(str, value))})"
                else:
                    url += f"&{key}=eq.{value}"
        
        if limit:
            url += f"&limit={limit}"
        
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()


def get_supabase_client():
    """Get simple Supabase client."""
    return SimpleSupabaseClient(SUPABASE_URL, SUPABASE_KEY)

# API Keys
VOYAGE_API_KEY = os.getenv("VOYAGE_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

# Test queries for evaluation
TEST_QUERIES = [
    # Condition-based
    "diabetes clinical trial with insulin treatment",
    "breast cancer immunotherapy phase 3",
    "obesity treatment with GLP-1 agonist",
    
    # PI-focused
    "experienced oncology principal investigator",
    "diabetes researcher with high publication record",
    
    # Site-focused
    "academic medical center in Germany",
    "cancer research hospital in United States",
    
    # Intervention-focused
    "monoclonal antibody treatment for cancer",
    "gene therapy clinical trial",
    
    # Complex queries
    "phase 2 diabetes trial with metformin at university hospital",
]

# Models to compare
MODELS = {
    "voyage-3.5-lite": {
        "provider": "voyage",
        "dimensions": 1024,
        "price_per_million": 0.02,
    },
    "voyage-4": {
        "provider": "voyage",
        "dimensions": 1024,
        "price_per_million": 0.02,
    },
    "text-embedding-3-small": {
        "provider": "openai",
        "dimensions": 1536,
        "price_per_million": 0.02,
    },
    "text-embedding-3-large": {
        "provider": "openai",
        "dimensions": 3072,
        "price_per_million": 0.13,
    },
}

# Optional: Add Gemini if API key available
if GOOGLE_API_KEY:
    MODELS["gemini-embedding-2"] = {
        "provider": "google",
        "dimensions": 1536,  # truncated from 3072
        "price_per_million": 0.10,
    }


class EmbeddingClient:
    """Unified client for multiple embedding providers."""
    
    def __init__(self):
        self.voyage_client = None
        self.openai_client = None
        self.google_configured = False
        
        if VOYAGE_API_KEY:
            try:
                import voyageai
                self.voyage_client = voyageai.Client(api_key=VOYAGE_API_KEY)
            except ImportError:
                print("⚠️  voyageai not installed")
        
        if OPENAI_API_KEY:
            try:
                from openai import OpenAI
                self.openai_client = OpenAI(api_key=OPENAI_API_KEY)
            except ImportError:
                print("⚠️  openai not installed")
        
        if GOOGLE_API_KEY:
            try:
                import google.generativeai as genai
                genai.configure(api_key=GOOGLE_API_KEY)
                self.google_configured = True
            except ImportError:
                print("⚠️  google-generativeai not installed")
    
    def embed_documents(self, texts: list[str], model: str) -> list[list[float]]:
        """Generate embeddings for documents."""
        config = MODELS.get(model)
        if not config:
            raise ValueError(f"Unknown model: {model}")
        
        provider = config["provider"]
        
        if provider == "voyage":
            return self._embed_voyage(texts, model, "document")
        elif provider == "openai":
            return self._embed_openai(texts, model)
        elif provider == "google":
            return self._embed_google(texts, "RETRIEVAL_DOCUMENT")
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def embed_query(self, query: str, model: str) -> list[float]:
        """Generate embedding for a query."""
        config = MODELS.get(model)
        if not config:
            raise ValueError(f"Unknown model: {model}")
        
        provider = config["provider"]
        
        if provider == "voyage":
            result = self._embed_voyage([query], model, "query")
            return result[0]
        elif provider == "openai":
            result = self._embed_openai([query], model)
            return result[0]
        elif provider == "google":
            result = self._embed_google([query], "RETRIEVAL_QUERY")
            return result[0]
        else:
            raise ValueError(f"Unknown provider: {provider}")
    
    def _embed_voyage(self, texts: list[str], model: str, input_type: str) -> list[list[float]]:
        if not self.voyage_client:
            raise RuntimeError("Voyage client not initialized")
        
        result = self.voyage_client.embed(
            texts,
            model=model,
            input_type=input_type,
            output_dimension=MODELS[model]["dimensions"]
        )
        return result.embeddings
    
    def _embed_openai(self, texts: list[str], model: str) -> list[list[float]]:
        if not self.openai_client:
            raise RuntimeError("OpenAI client not initialized")
        
        response = self.openai_client.embeddings.create(
            model=model,
            input=texts
        )
        return [item.embedding for item in response.data]
    
    def _embed_google(self, texts: list[str], task_type: str) -> list[list[float]]:
        if not self.google_configured:
            raise RuntimeError("Google API not configured")
        
        import google.generativeai as genai
        
        # Use batch embedding for speed (up to 100 texts per batch)
        result = genai.embed_content(
            model="models/gemini-embedding-001",
            content=texts,  # Pass all texts at once
            task_type=task_type,
            output_dimensionality=1536
        )
        return result['embedding']


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Calculate cosine similarity between two vectors."""
    a = np.array(a)
    b = np.array(b)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def load_sample_trials(sample_size: int) -> list[dict]:
    """Load a sample of trials from the subset."""
    client = get_supabase_client()
    ids_file = DATA_DIR / "subset_trial_ids.json"
    
    if ids_file.exists():
        with open(ids_file) as f:
            trial_ids = json.load(f)[:sample_size]
    else:
        # Fall back to random sample from database
        result = client.query("trials", select="id", limit=sample_size)
        trial_ids = [r["id"] for r in result]
    
    # Fetch trial details in batches
    trials = []
    for i in range(0, len(trial_ids), 100):
        batch = trial_ids[i:i + 100]
        result = client.query(
            "trials",
            select="id,nct_id,brief_title,brief_summary,conditions,phase",
            filters={"id": batch}
        )
        trials.extend(result)
    
    return trials


def build_embedding_text(trial: dict) -> str:
    """Build embedding text for a trial."""
    parts = []
    
    if trial.get("brief_title"):
        parts.append(f"Title: {trial['brief_title']}")
    if trial.get("brief_summary"):
        summary = trial["brief_summary"][:800]
        parts.append(f"Summary: {summary}")
    if trial.get("conditions"):
        parts.append(f"Conditions: {', '.join(trial['conditions'][:5])}")
    if trial.get("phase"):
        parts.append(f"Phase: {trial['phase']}")
    
    return "\n".join(parts)


def evaluate_model(
    client: EmbeddingClient,
    model: str,
    trials: list[dict],
    queries: list[str]
) -> dict:
    """Evaluate a model on the test set."""
    print(f"\n📊 Evaluating {model}...")
    
    config = MODELS[model]
    results = {
        "model": model,
        "dimensions": config["dimensions"],
        "price_per_million": config["price_per_million"],
        "query_results": [],
        "avg_similarity": 0,
        "top_k_precision": 0,
        "embedding_time": 0,
        "query_time": 0,
    }
    
    # Build embedding texts
    texts = [build_embedding_text(t) for t in trials]
    
    # Generate document embeddings
    print(f"   Embedding {len(texts)} documents...")
    start = time.time()
    try:
        doc_embeddings = client.embed_documents(texts, model)
        results["embedding_time"] = time.time() - start
        print(f"   ✓ Documents embedded in {results['embedding_time']:.2f}s")
    except Exception as e:
        print(f"   ❌ Error embedding documents: {e}")
        results["error"] = str(e)
        return results
    
    # Evaluate each query
    print(f"   Testing {len(queries)} queries...")
    all_similarities = []
    
    for query in queries:
        try:
            start = time.time()
            query_embedding = client.embed_query(query, model)
            query_time = time.time() - start
            results["query_time"] += query_time
            
            # Calculate similarities
            similarities = [
                (i, cosine_similarity(query_embedding, doc_emb))
                for i, doc_emb in enumerate(doc_embeddings)
            ]
            similarities.sort(key=lambda x: x[1], reverse=True)
            
            # Get top 5 results
            top_5 = similarities[:5]
            top_5_trials = [
                {
                    "nct_id": trials[i]["nct_id"],
                    "title": trials[i]["brief_title"][:50],
                    "similarity": sim
                }
                for i, sim in top_5
            ]
            
            results["query_results"].append({
                "query": query,
                "top_similarity": top_5[0][1],
                "avg_top5_similarity": sum(s for _, s in top_5) / 5,
                "top_results": top_5_trials
            })
            
            all_similarities.append(top_5[0][1])
            
        except Exception as e:
            print(f"   ❌ Error on query '{query[:30]}...': {e}")
    
    # Calculate aggregate metrics
    if all_similarities:
        results["avg_similarity"] = sum(all_similarities) / len(all_similarities)
    
    results["query_time"] /= len(queries)  # Average per query
    
    print(f"   ✓ Avg top similarity: {results['avg_similarity']:.4f}")
    print(f"   ✓ Avg query time: {results['query_time']*1000:.1f}ms")
    
    return results


def print_comparison(results: list[dict]):
    """Print comparison table."""
    print("\n" + "="*80)
    print("📊 EMBEDDING MODEL COMPARISON RESULTS")
    print("="*80)
    
    # Filter out errored results
    valid_results = [r for r in results if "error" not in r]
    
    if not valid_results:
        print("❌ No valid results to compare")
        return
    
    # Sort by avg similarity
    valid_results.sort(key=lambda x: x["avg_similarity"], reverse=True)
    
    print(f"\n{'Model':<25} {'Dims':>6} {'Avg Sim':>8} {'Embed(s)':>9} {'Query(ms)':>10} {'$/1M':>8}")
    print("-"*80)
    
    for r in valid_results:
        print(f"{r['model']:<25} {r['dimensions']:>6} {r['avg_similarity']:>8.4f} "
              f"{r['embedding_time']:>9.2f} {r['query_time']*1000:>10.1f} ${r['price_per_million']:>7.2f}")
    
    # Winner
    winner = valid_results[0]
    print("\n" + "="*80)
    print(f"🏆 WINNER: {winner['model']}")
    print(f"   Avg similarity: {winner['avg_similarity']:.4f}")
    print(f"   Dimensions: {winner['dimensions']}")
    print(f"   Price: ${winner['price_per_million']}/1M tokens")
    print("="*80)
    
    # Sample query results from winner
    print(f"\n📝 Sample results from {winner['model']}:")
    for qr in winner["query_results"][:3]:
        print(f"\n   Query: \"{qr['query'][:50]}...\"")
        print(f"   Top similarity: {qr['top_similarity']:.4f}")
        for i, tr in enumerate(qr["top_results"][:2]):
            print(f"      {i+1}. [{tr['nct_id']}] {tr['title']}... ({tr['similarity']:.3f})")


def main(args):
    print("🔬 Embedding Model Comparison")
    print("="*60)
    
    # Check available models
    available_models = []
    
    if VOYAGE_API_KEY:
        available_models.extend(["voyage-3.5-lite", "voyage-4"])
        print("✅ Voyage API key found")
    else:
        print("⚠️  VOYAGE_API_KEY not found - skipping Voyage models")
    
    if OPENAI_API_KEY:
        available_models.extend(["text-embedding-3-small", "text-embedding-3-large"])
        print("✅ OpenAI API key found")
    else:
        print("⚠️  OPENAI_API_KEY not found - skipping OpenAI models")
    
    if GOOGLE_API_KEY:
        available_models.append("gemini-embedding-2")
        print("✅ Google API key found")
    else:
        print("ℹ️  GOOGLE_API_KEY not found - skipping Gemini (optional)")
    
    if not available_models:
        print("\n❌ No API keys found! Add at least one to .env")
        return
    
    print(f"\n📋 Models to test: {', '.join(available_models)}")
    
    # Load sample trials
    trials = load_sample_trials(args.sample_size)
    print(f"📥 Loaded {len(trials)} sample trials")
    
    # Initialize client
    client = EmbeddingClient()
    
    # Evaluate each model
    all_results = []
    for model in available_models:
        try:
            result = evaluate_model(client, model, trials, TEST_QUERIES)
            all_results.append(result)
            time.sleep(1)  # Rate limiting between models
        except Exception as e:
            print(f"❌ Failed to evaluate {model}: {e}")
            all_results.append({"model": model, "error": str(e)})
    
    # Print comparison
    print_comparison(all_results)
    
    # Save results
    results_file = DATA_DIR / "embedding_comparison_results.json"
    DATA_DIR.mkdir(exist_ok=True)
    with open(results_file, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\n💾 Results saved to {results_file}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compare embedding models")
    parser.add_argument("--sample-size", type=int, default=100, 
                        help="Number of trials to test (default: 100)")
    
    args = parser.parse_args()
    main(args)
