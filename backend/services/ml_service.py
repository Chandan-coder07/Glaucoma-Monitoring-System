"""
ML service — RandomForest glaucoma risk predictor.
Warnings from sklearn.utils.parallel suppressed cleanly.
"""
import os
import pickle
import warnings
import logging
from pathlib import Path
from typing import Tuple

# Suppress sklearn parallel warnings globally before any sklearn import
os.environ["PYTHONWARNINGS"] = "ignore::UserWarning:sklearn"
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
logging.getLogger("sklearn").setLevel(logging.ERROR)

import numpy as np

MODEL_PATH = Path(__file__).parent.parent / "ml" / "glaucoma_model.pkl"


def _synthetic_dataset():
    rng    = np.random.default_rng(42)
    n      = 2000
    iop    = rng.normal(18, 4, n).clip(8, 35)
    age    = rng.normal(55, 15, n).clip(20, 90)
    cornea = rng.normal(540, 35, n).clip(440, 640)

    labels = np.zeros(n, dtype=int)
    high   = (iop > 24) | ((iop > 21) & (cornea < 500)) | ((iop > 21) & (age > 70))
    medium = ~high & ((iop > 18) | ((iop > 16) & (age > 60)))
    labels[high]   = 2
    labels[medium] = 1
    return np.column_stack([iop, age, cornea]), labels


def _train() -> object:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.model_selection import train_test_split

        print("🧠 Training glaucoma risk model...")
        X, y = _synthetic_dataset()
        Xtr, Xte, ytr, yte = train_test_split(X, y, test_size=0.2, random_state=42)

        clf = RandomForestClassifier(
            n_estimators=100,
            max_depth=8,
            class_weight="balanced",
            random_state=42,
            n_jobs=1,   # n_jobs=1 avoids the parallel warning entirely
        )
        clf.fit(Xtr, ytr)

        acc = (clf.predict(Xte) == yte).mean()
        print(f"✅ Model trained — accuracy: {acc:.1%}")

        MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(MODEL_PATH, "wb") as f:
            pickle.dump(clf, f)
        print(f"✅ Model saved → {MODEL_PATH}")
        return clf


def _load() -> object:
    if MODEL_PATH.exists():
        with open(MODEL_PATH, "rb") as f:
            clf = pickle.load(f)
        # Patch existing models to use n_jobs=1 to suppress warnings
        if hasattr(clf, 'n_jobs') and clf.n_jobs != 1:
            clf.n_jobs = 1
        print(f"✅ ML model loaded from {MODEL_PATH}")
        return clf
    return _train()


_clf    = _load()
_LABELS = {0: "LOW", 1: "MEDIUM", 2: "HIGH"}


def predict_risk(iop: float, age: int, cornea_thickness: float) -> Tuple[str, float]:
    """Return (risk_label, probability). Thread-safe, no warnings."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        X     = np.array([[iop, age, cornea_thickness]])
        pred  = int(_clf.predict(X)[0])
        proba = float(_clf.predict_proba(X)[0][pred])
    return _LABELS[pred], proba


def get_risk_summary(measurements: list) -> dict:
    if not measurements:
        return {"avg_iop": 0, "max_iop": 0, "min_iop": 0,
                "total_measurements": 0, "risk_distribution": {}}
    iops = [m["iop_value"] for m in measurements]
    dist = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    for m in measurements:
        dist[m.get("risk_level", "LOW")] += 1
    return {
        "avg_iop":            round(sum(iops) / len(iops), 2),
        "max_iop":            max(iops),
        "min_iop":            min(iops),
        "total_measurements": len(measurements),
        "risk_distribution":  dist,
    }