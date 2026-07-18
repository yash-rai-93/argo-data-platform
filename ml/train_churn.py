"""Train and persist an XGBoost churn classifier."""

from __future__ import annotations

from pathlib import Path

import xgboost as xgb
from sklearn.metrics import accuracy_score, roc_auc_score
from sklearn.model_selection import train_test_split

from ml.feature_extractor import ChurnFeatureExtractor

_MODEL_PATH = Path(__file__).resolve().parent / "models" / "churn_xgb.json"
_FEATURES = ["total_sessions", "avg_session_duration", "account_age_days"]


def main() -> None:
    """Load features, train the model, report metrics, and save the artifact."""
    frame = ChurnFeatureExtractor().extract_features()
    features = frame[_FEATURES]
    target = frame["is_churned"]

    x_train, x_test, y_train, y_test = train_test_split(
        features, target, test_size=0.2, random_state=42, stratify=target
    )

    model = xgb.XGBClassifier(eval_metric="logloss", random_state=42)
    model.fit(x_train, y_train)

    predictions = model.predict(x_test)
    probabilities = model.predict_proba(x_test)[:, 1]
    print(f"Accuracy: {accuracy_score(y_test, predictions):.4f}")
    print(f"ROC-AUC:  {roc_auc_score(y_test, probabilities):.4f}")

    _MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    model.save_model(_MODEL_PATH)
    print(f"Saved model to {_MODEL_PATH}")


if __name__ == "__main__":
    main()
