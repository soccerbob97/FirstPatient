"""
Integrate ML-based scoring into the recommendation system.

This script provides:
1. MLScorer class that loads the trained model and computes scores
2. Integration code to replace/augment the heuristic scoring in recommender.py
"""

import os
import sys
import json
import numpy as np
from typing import Optional

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False
    print("Warning: lightgbm not installed. ML scoring will be disabled.")


class MLScorer:
    """
    ML-based scorer for PI success prediction.
    
    Uses a trained LightGBM model to predict the probability that
    a PI will successfully complete a trial similar to the query.
    """
    
    def __init__(self, model_dir: Optional[str] = None):
        """
        Initialize the ML scorer.
        
        Args:
            model_dir: Path to directory containing model files.
                      If None, uses default location.
        """
        self.model = None
        self.feature_names = None
        self.is_loaded = False
        
        if not HAS_LIGHTGBM:
            print("MLScorer: lightgbm not available, using fallback scoring")
            return
        
        if model_dir is None:
            model_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "model"
            )
        
        self._load_model(model_dir)
    
    def _load_model(self, model_dir: str):
        """Load the trained model and feature names."""
        model_path = os.path.join(model_dir, "pi_success_model.txt")
        features_path = os.path.join(model_dir, "feature_names.json")
        
        if not os.path.exists(model_path):
            print(f"MLScorer: Model not found at {model_path}")
            return
        
        try:
            self.model = lgb.Booster(model_file=model_path)
            
            with open(features_path, "r") as f:
                self.feature_names = json.load(f)
            
            self.is_loaded = True
            print(f"MLScorer: Loaded model with {len(self.feature_names)} features")
            
        except Exception as e:
            print(f"MLScorer: Failed to load model: {e}")
    
    def compute_features(
        self,
        pi_data: dict,
        trial_data: dict,
        historical_stats: dict,
    ) -> np.ndarray:
        """
        Compute feature vector for a PI-trial pair.
        
        Args:
            pi_data: PI information (id, name, role, affiliation)
            trial_data: Trial/query information (phase, condition, enrollment, sponsor)
            historical_stats: Pre-computed PI historical stats
                - prior_trials: int
                - prior_completed: int
                - prior_same_condition: int
                - prior_same_phase: int
        
        Returns:
            Feature vector as numpy array
        """
        # Initialize feature dict with zeros
        features = {name: 0.0 for name in self.feature_names}
        
        # PI Features
        prior_trials = historical_stats.get("prior_trials", 0)
        prior_completed = historical_stats.get("prior_completed", 0)
        
        features["pi_prior_trials"] = prior_trials
        features["pi_prior_completed"] = prior_completed
        features["pi_prior_completion_rate"] = (
            prior_completed / prior_trials if prior_trials > 0 else 0.5
        )
        features["pi_prior_same_condition"] = historical_stats.get("prior_same_condition", 0)
        features["pi_prior_same_phase"] = historical_stats.get("prior_same_phase", 0)
        features["pi_has_affiliation"] = 1 if pi_data.get("affiliation") else 0
        
        # Role Features
        role = pi_data.get("role", "").upper()
        features["role_is_pi"] = 1 if role == "PRINCIPAL_INVESTIGATOR" else 0
        features["role_is_director"] = 1 if role == "STUDY_DIRECTOR" else 0
        features["role_is_chair"] = 1 if role == "STUDY_CHAIR" else 0
        
        # Trial Features
        features["trial_enrollment"] = trial_data.get("enrollment", 0) or 0
        
        # Categorical features (one-hot encoded)
        phase = trial_data.get("phase", "")
        condition = trial_data.get("condition", "").lower()
        sponsor = trial_data.get("sponsor_class", "UNKNOWN")
        
        # Set one-hot encoded features
        phase_col = f"trial_phase_{phase}"
        if phase_col in features:
            features[phase_col] = 1
        
        condition_col = f"trial_condition_{condition}"
        if condition_col in features:
            features[condition_col] = 1
        
        sponsor_col = f"trial_sponsor_class_{sponsor}"
        if sponsor_col in features:
            features[sponsor_col] = 1
        
        # Convert to array in correct order
        return np.array([features[name] for name in self.feature_names])
    
    def predict(
        self,
        pi_data: dict,
        trial_data: dict,
        historical_stats: dict,
    ) -> float:
        """
        Predict success probability for a PI-trial pair.
        
        Returns:
            Probability between 0 and 1
        """
        if not self.is_loaded:
            # Fallback to simple heuristic
            return self._fallback_score(historical_stats)
        
        features = self.compute_features(pi_data, trial_data, historical_stats)
        features = features.reshape(1, -1)
        
        prob = self.model.predict(features)[0]
        return float(prob)
    
    def predict_batch(
        self,
        candidates: list[dict],
        trial_data: dict,
    ) -> list[float]:
        """
        Predict success probabilities for multiple PI candidates.
        
        Args:
            candidates: List of dicts with pi_data and historical_stats
            trial_data: Common trial/query information
        
        Returns:
            List of probabilities
        """
        if not self.is_loaded:
            return [
                self._fallback_score(c.get("historical_stats", {}))
                for c in candidates
            ]
        
        # Build feature matrix
        feature_matrix = np.array([
            self.compute_features(
                c.get("pi_data", {}),
                trial_data,
                c.get("historical_stats", {}),
            )
            for c in candidates
        ])
        
        probs = self.model.predict(feature_matrix)
        return [float(p) for p in probs]
    
    def _fallback_score(self, historical_stats: dict) -> float:
        """Simple heuristic fallback when model is not available."""
        prior_trials = historical_stats.get("prior_trials", 0)
        prior_completed = historical_stats.get("prior_completed", 0)
        
        if prior_trials == 0:
            return 0.5  # No history, neutral score
        
        completion_rate = prior_completed / prior_trials
        # Blend with prior (Bayesian smoothing)
        # Assume prior of 0.7 completion rate with strength of 2 trials
        smoothed = (prior_completed + 0.7 * 2) / (prior_trials + 2)
        
        return smoothed


class HybridScorer:
    """
    Combines ML-based success prediction with semantic similarity.
    
    Final score = α * semantic_similarity + β * ml_success_prob + γ * role_confidence
    
    Where α + β + γ = 1
    """
    
    def __init__(
        self,
        similarity_weight: float = 0.50,
        ml_weight: float = 0.35,
        role_weight: float = 0.15,
        model_dir: Optional[str] = None,
    ):
        """
        Initialize hybrid scorer.
        
        Args:
            similarity_weight: Weight for semantic similarity (default 0.50)
            ml_weight: Weight for ML success prediction (default 0.35)
            role_weight: Weight for role confidence (default 0.15)
            model_dir: Path to ML model directory
        """
        self.weights = {
            "similarity": similarity_weight,
            "ml_success": ml_weight,
            "role": role_weight,
        }
        
        # Validate weights sum to 1
        total = sum(self.weights.values())
        if abs(total - 1.0) > 0.01:
            print(f"Warning: Weights sum to {total}, normalizing...")
            for k in self.weights:
                self.weights[k] /= total
        
        self.ml_scorer = MLScorer(model_dir)
        
        # Role confidence scores
        self.role_confidence = {
            "PRINCIPAL_INVESTIGATOR": 1.0,
            "STUDY_DIRECTOR": 0.95,
            "STUDY_CHAIR": 0.90,
            "SUB_INVESTIGATOR": 0.70,
            "CONTACT": 0.50,
            "trial_match": 0.40,
        }
    
    def score(
        self,
        similarity: float,
        pi_data: dict,
        trial_data: dict,
        historical_stats: dict,
    ) -> dict:
        """
        Compute hybrid score for a PI-trial pair.
        
        Args:
            similarity: Semantic similarity score (0-1)
            pi_data: PI information
            trial_data: Trial/query information
            historical_stats: PI historical statistics
        
        Returns:
            Dict with component scores and final score
        """
        # ML success prediction
        ml_prob = self.ml_scorer.predict(pi_data, trial_data, historical_stats)
        
        # Role confidence
        role = pi_data.get("role", "trial_match")
        role_score = self.role_confidence.get(role, 0.4)
        
        # Weighted combination
        final = (
            self.weights["similarity"] * similarity +
            self.weights["ml_success"] * ml_prob +
            self.weights["role"] * role_score
        )
        
        return {
            "similarity": round(similarity, 4),
            "ml_success_prob": round(ml_prob, 4),
            "role_confidence": round(role_score, 4),
            "final": round(final, 4),
        }
    
    def score_batch(
        self,
        candidates: list[dict],
        trial_data: dict,
    ) -> list[dict]:
        """
        Score multiple candidates efficiently.
        
        Args:
            candidates: List of dicts with:
                - similarity: float
                - pi_data: dict
                - historical_stats: dict
            trial_data: Common trial/query information
        
        Returns:
            List of score dicts
        """
        # Batch ML predictions
        ml_probs = self.ml_scorer.predict_batch(
            [{"pi_data": c["pi_data"], "historical_stats": c["historical_stats"]} 
             for c in candidates],
            trial_data,
        )
        
        results = []
        for c, ml_prob in zip(candidates, ml_probs):
            similarity = c.get("similarity", 0.5)
            role = c.get("pi_data", {}).get("role", "trial_match")
            role_score = self.role_confidence.get(role, 0.4)
            
            final = (
                self.weights["similarity"] * similarity +
                self.weights["ml_success"] * ml_prob +
                self.weights["role"] * role_score
            )
            
            results.append({
                "similarity": round(similarity, 4),
                "ml_success_prob": round(ml_prob, 4),
                "role_confidence": round(role_score, 4),
                "final": round(final, 4),
            })
        
        return results


# Example usage and integration code
def example_integration():
    """
    Example showing how to integrate HybridScorer into recommender.py
    """
    print("=" * 60)
    print("Example: Integrating ML Scoring into Recommender")
    print("=" * 60)
    
    # Initialize scorer
    scorer = HybridScorer(
        similarity_weight=0.50,
        ml_weight=0.35,
        role_weight=0.15,
    )
    
    # Example candidate
    candidate = {
        "similarity": 0.82,
        "pi_data": {
            "id": 12345,
            "name": "Dr. Jane Smith",
            "role": "PRINCIPAL_INVESTIGATOR",
            "affiliation": "Mayo Clinic",
        },
        "historical_stats": {
            "prior_trials": 15,
            "prior_completed": 12,
            "prior_same_condition": 5,
            "prior_same_phase": 8,
        },
    }
    
    trial_data = {
        "phase": "PHASE2",
        "condition": "diabetes",
        "enrollment": 200,
        "sponsor_class": "INDUSTRY",
    }
    
    # Score the candidate
    scores = scorer.score(
        similarity=candidate["similarity"],
        pi_data=candidate["pi_data"],
        trial_data=trial_data,
        historical_stats=candidate["historical_stats"],
    )
    
    print(f"\nCandidate: {candidate['pi_data']['name']}")
    print(f"  Similarity: {scores['similarity']}")
    print(f"  ML Success Prob: {scores['ml_success_prob']}")
    print(f"  Role Confidence: {scores['role_confidence']}")
    print(f"  Final Score: {scores['final']}")
    
    print("\n" + "=" * 60)
    print("To integrate into recommender.py:")
    print("=" * 60)
    print("""
1. Import the HybridScorer:
   from scripts.ml_scoring.03_integrate_scoring import HybridScorer

2. Initialize in PIRecommender.__init__():
   self.hybrid_scorer = HybridScorer()

3. Replace _calculate_score() with:
   def _calculate_score(self, row: dict, trial_data: dict) -> dict:
       return self.hybrid_scorer.score(
           similarity=row["avg_trial_similarity"],
           pi_data={
               "role": row["link_type"],
               "affiliation": row.get("affiliation"),
           },
           trial_data=trial_data,
           historical_stats={
               "prior_trials": row["total_trials"],
               "prior_completed": int(row["total_trials"] * row.get("completion_rate", 0.5)),
               "prior_same_condition": row.get("same_condition_trials", 0),
               "prior_same_phase": row.get("same_phase_trials", 0),
           },
       )
""")


if __name__ == "__main__":
    example_integration()
