"""
Train and evaluate the AI call-progress classifier.

Loads ``data/audio_dataset/dataset.npz`` (built by build_audio_dataset.py),
trains a calibrated RandomForest, reports held-out accuracy + a confusion
matrix + cross-validation, and saves the shippable model bundle to
``models/call_progress_model.joblib``.

Run:  python scripts/train_call_model.py
"""
from __future__ import annotations

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.call_audio_ai import FEATURE_NAMES, LABELS  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET = os.path.join(ROOT, "data", "audio_dataset", "dataset.npz")
MODEL_DIR = os.path.join(ROOT, "models")
MODEL_PATH = os.path.join(MODEL_DIR, "call_progress_model.joblib")


def main() -> None:
    if not os.path.exists(DATASET):
        print("Dataset missing — run scripts/build_audio_dataset.py first.")
        sys.exit(1)

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.metrics import classification_report, confusion_matrix
    from sklearn.model_selection import StratifiedKFold, cross_val_score, train_test_split
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    data = np.load(DATASET, allow_pickle=True)
    X, y = data["X"], data["y"]
    labels = list(data["labels"]) if "labels" in data else LABELS
    print(f"Loaded {X.shape[0]} samples × {X.shape[1]} features, "
          f"{len(labels)} classes: {labels}")

    X_tr, X_te, y_tr, y_te = train_test_split(
        X, y, test_size=0.25, random_state=42, stratify=y)

    clf = Pipeline([
        ("scaler", StandardScaler()),
        ("rf", RandomForestClassifier(
            n_estimators=300, max_depth=None, min_samples_leaf=2,
            class_weight="balanced", n_jobs=-1, random_state=42)),
    ])

    print("\nCross-validating (5-fold)…")
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    scores = cross_val_score(clf, X, y, cv=cv, scoring="accuracy", n_jobs=-1)
    print(f"  CV accuracy: {scores.mean():.4f} ± {scores.std():.4f}")

    clf.fit(X_tr, y_tr)
    y_pred = clf.predict(X_te)
    acc = float((y_pred == y_te).mean())
    print(f"\nHeld-out test accuracy: {acc:.4f}\n")
    print(classification_report(y_te, y_pred, target_names=labels, digits=3))
    print("Confusion matrix (rows=true, cols=pred):")
    cm = confusion_matrix(y_te, y_pred)
    header = "          " + "".join(f"{lab[:8]:>9}" for lab in labels)
    print(header)
    for i, lab in enumerate(labels):
        print(f"{lab:>9} " + "".join(f"{cm[i, j]:>9d}" for j in range(len(labels))))

    # Refit on ALL data for the shipped model.
    clf.fit(X, y)
    os.makedirs(MODEL_DIR, exist_ok=True)
    import joblib
    joblib.dump({
        "model": clf,
        "labels": labels,
        "feature_names": FEATURE_NAMES,
        "cv_accuracy": float(scores.mean()),
        "test_accuracy": acc,
    }, MODEL_PATH)
    print(f"\nSaved model → {MODEL_PATH}")


if __name__ == "__main__":
    main()
