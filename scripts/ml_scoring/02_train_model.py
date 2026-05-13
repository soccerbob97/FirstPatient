"""
Train PI Success Prediction Model using LightGBM.

This script trains a gradient boosted model to predict whether a PI
will successfully complete a trial based on historical features.

Model: LightGBM with binary classification
Evaluation: AUC-ROC, Precision, Recall, Feature Importance
"""

import os
import sys
import json
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.model_selection import train_test_split, cross_val_score
from sklearn.metrics import (
    roc_auc_score, precision_score, recall_score, f1_score,
    classification_report, confusion_matrix
)
import lightgbm as lgb
import joblib

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# Feature columns for the model
FEATURE_COLUMNS = [
    # PI Features
    "pi_prior_trials",
    "pi_prior_completed", 
    "pi_prior_completion_rate",
    "pi_prior_same_condition",
    "pi_prior_same_phase",
    "pi_has_affiliation",
    
    # Role Features
    "role_is_pi",
    "role_is_director",
    "role_is_chair",
    
    # Trial Features (numeric)
    "trial_enrollment",
]

# Categorical features that need encoding
CATEGORICAL_COLUMNS = [
    "trial_phase",
    "trial_condition",
    "trial_sponsor_class",
]


def load_training_data(data_path):
    """Load training data from JSON file."""
    print(f"Loading training data from {data_path}...")
    
    with open(data_path, "r") as f:
        data = json.load(f)
    
    examples = data["examples"]
    metadata = data["metadata"]
    
    print(f"  Total examples: {metadata['total_examples']}")
    print(f"  Positive rate: {100 * metadata['positive_examples'] / metadata['total_examples']:.1f}%")
    
    return pd.DataFrame(examples), metadata


def prepare_features(df):
    """Prepare feature matrix for training."""
    print("Preparing features...")
    
    # Copy numeric features
    X = df[FEATURE_COLUMNS].copy()
    
    # One-hot encode categorical features
    for col in CATEGORICAL_COLUMNS:
        if col in df.columns:
            dummies = pd.get_dummies(df[col], prefix=col, dummy_na=True)
            X = pd.concat([X, dummies], axis=1)
    
    # Fill NaN with 0 for numeric columns
    X = X.fillna(0)
    
    # Get labels
    y = df["label"].values
    
    print(f"  Feature matrix shape: {X.shape}")
    print(f"  Features: {list(X.columns)}")
    
    return X, y


def train_model(X_train, y_train, X_val, y_val):
    """Train LightGBM model."""
    print("\nTraining LightGBM model...")
    
    # Create datasets
    train_data = lgb.Dataset(X_train, label=y_train)
    val_data = lgb.Dataset(X_val, label=y_val, reference=train_data)
    
    # Model parameters
    params = {
        "objective": "binary",
        "metric": "auc",
        "boosting_type": "gbdt",
        "num_leaves": 31,
        "learning_rate": 0.05,
        "feature_fraction": 0.8,
        "bagging_fraction": 0.8,
        "bagging_freq": 5,
        "verbose": -1,
        "seed": 42,
        # Handle class imbalance
        "is_unbalance": True,
    }
    
    # Train with early stopping
    model = lgb.train(
        params,
        train_data,
        num_boost_round=500,
        valid_sets=[train_data, val_data],
        valid_names=["train", "val"],
        callbacks=[
            lgb.early_stopping(stopping_rounds=50),
            lgb.log_evaluation(period=50),
        ],
    )
    
    return model


def evaluate_model(model, X_test, y_test, feature_names):
    """Evaluate model performance."""
    print("\n" + "=" * 60)
    print("Model Evaluation")
    print("=" * 60)
    
    # Predictions
    y_pred_proba = model.predict(X_test)
    y_pred = (y_pred_proba >= 0.5).astype(int)
    
    # Metrics
    auc = roc_auc_score(y_test, y_pred_proba)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    
    print(f"\nTest Set Metrics:")
    print(f"  AUC-ROC: {auc:.4f}")
    print(f"  Precision: {precision:.4f}")
    print(f"  Recall: {recall:.4f}")
    print(f"  F1 Score: {f1:.4f}")
    
    print(f"\nClassification Report:")
    print(classification_report(y_test, y_pred, target_names=["Failed", "Completed"]))
    
    print(f"\nConfusion Matrix:")
    cm = confusion_matrix(y_test, y_pred)
    print(f"  TN={cm[0,0]}, FP={cm[0,1]}")
    print(f"  FN={cm[1,0]}, TP={cm[1,1]}")
    
    # Feature importance
    print(f"\nTop 15 Feature Importances:")
    importance = pd.DataFrame({
        "feature": feature_names,
        "importance": model.feature_importance(importance_type="gain")
    }).sort_values("importance", ascending=False)
    
    for i, row in importance.head(15).iterrows():
        print(f"  {row['feature']}: {row['importance']:.2f}")
    
    return {
        "auc": auc,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "feature_importance": importance.to_dict("records"),
    }


def save_model(model, feature_names, metrics, output_dir):
    """Save trained model and metadata."""
    print(f"\nSaving model to {output_dir}...")
    
    os.makedirs(output_dir, exist_ok=True)
    
    # Save model
    model_path = os.path.join(output_dir, "pi_success_model.txt")
    model.save_model(model_path)
    print(f"  Model saved to {model_path}")
    
    # Save feature names (needed for inference)
    features_path = os.path.join(output_dir, "feature_names.json")
    with open(features_path, "w") as f:
        json.dump(feature_names, f)
    print(f"  Feature names saved to {features_path}")
    
    # Save metrics and metadata
    metadata_path = os.path.join(output_dir, "model_metadata.json")
    with open(metadata_path, "w") as f:
        json.dump({
            "created_at": datetime.now().isoformat(),
            "model_type": "lightgbm",
            "metrics": {k: v for k, v in metrics.items() if k != "feature_importance"},
            "feature_importance": metrics["feature_importance"][:20],  # Top 20
            "num_features": len(feature_names),
        }, f, indent=2)
    print(f"  Metadata saved to {metadata_path}")


def main():
    print("=" * 60)
    print("PI Success Prediction - Model Training")
    print("=" * 60)
    
    # Paths
    script_dir = os.path.dirname(os.path.abspath(__file__))
    data_path = os.path.join(script_dir, "training_data.json")
    output_dir = os.path.join(script_dir, "model")
    
    # Check if training data exists
    if not os.path.exists(data_path):
        print(f"ERROR: Training data not found at {data_path}")
        print("Please run 01_extract_training_data.py first.")
        return
    
    # Load data
    df, metadata = load_training_data(data_path)
    
    # Prepare features
    X, y = prepare_features(df)
    feature_names = list(X.columns)
    
    # Split data: 70% train, 15% val, 15% test
    X_train_val, X_test, y_train_val, y_test = train_test_split(
        X, y, test_size=0.15, random_state=42, stratify=y
    )
    X_train, X_val, y_train, y_val = train_test_split(
        X_train_val, y_train_val, test_size=0.176, random_state=42, stratify=y_train_val
    )  # 0.176 of 0.85 ≈ 0.15 of total
    
    print(f"\nData splits:")
    print(f"  Train: {len(X_train)} examples")
    print(f"  Val: {len(X_val)} examples")
    print(f"  Test: {len(X_test)} examples")
    
    # Train model
    model = train_model(X_train, y_train, X_val, y_val)
    
    # Evaluate
    metrics = evaluate_model(model, X_test, y_test, feature_names)
    
    # Save
    save_model(model, feature_names, metrics, output_dir)
    
    print("\n" + "=" * 60)
    print("Training Complete!")
    print("=" * 60)
    print(f"\nNext steps:")
    print(f"  1. Review model performance (AUC={metrics['auc']:.4f})")
    print(f"  2. Run 03_integrate_scoring.py to integrate into recommender")


if __name__ == "__main__":
    main()
