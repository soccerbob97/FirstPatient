# ML-Based PI Success Scoring

This module implements a machine learning approach to score PI+Site recommendations based on historical trial success data.

## Overview

Instead of using hand-tuned heuristic weights, we train a model to predict:
> "Given a PI's historical performance, what's the probability they'll successfully complete a trial like this?"

### Success Definition
- **Positive (1)**: Trial status = `COMPLETED`
- **Negative (0)**: Trial status = `TERMINATED`, `WITHDRAWN`, or `SUSPENDED`

## Scripts

### 1. `01_extract_training_data.py`
Extracts training data from historical trials for diabetes, breast cancer, and obesity conditions.

**Features extracted:**
- **PI Features**: prior trial count, completion rate, condition-specific experience, phase experience
- **Role Features**: is_pi, is_director, is_chair
- **Trial Features**: phase, condition, enrollment, sponsor class

**Output**: `training_data.json`

```bash
python scripts/ml_scoring/01_extract_training_data.py
```

### 2. `02_train_model.py`
Trains a LightGBM model on the extracted data.

**Model**: LightGBM binary classifier with:
- Early stopping on validation set
- Class imbalance handling
- Feature importance analysis

**Output**: `model/` directory with:
- `pi_success_model.txt` - Trained model
- `feature_names.json` - Feature column names
- `model_metadata.json` - Metrics and metadata

```bash
python scripts/ml_scoring/02_train_model.py
```

### 3. `03_integrate_scoring.py`
Provides `MLScorer` and `HybridScorer` classes for integration.

**HybridScorer** combines:
- 50% Semantic similarity (vector search)
- 35% ML success probability (trained model)
- 15% Role confidence (PI > Director > Chair > Contact)

## Integration

To use in `recommender.py`:

```python
from scripts.ml_scoring.03_integrate_scoring import HybridScorer

class PIRecommender:
    def __init__(self):
        # ... existing init ...
        self.hybrid_scorer = HybridScorer()
    
    def _calculate_score(self, row: dict, trial_data: dict) -> dict:
        return self.hybrid_scorer.score(
            similarity=row["avg_trial_similarity"],
            pi_data={"role": row["link_type"], ...},
            trial_data=trial_data,
            historical_stats={"prior_trials": row["total_trials"], ...},
        )
```

## Requirements

```bash
pip install lightgbm scikit-learn pandas
```

## Model Performance

After training, check `model/model_metadata.json` for:
- AUC-ROC score
- Precision/Recall
- Top feature importances

Expected AUC: 0.65-0.75 (better than random, captures meaningful signal)

## Future Improvements

1. **Add S2 features**: h-index, paper count, citation count (after V2 enrichment)
2. **Site features**: site completion rate, institution type
3. **Temporal features**: years since last trial, recency weighting
4. **Cross-validation**: k-fold CV for more robust evaluation
5. **Online learning**: Update model as new trials complete
