"""Binary classification metrics from (scores in [0,1], hard labels).

Mirrors the metric set of the dino-bench harness so numbers from the two are
comparable, with one deliberate difference: a metric that cannot be computed
comes back as ``None`` rather than NaN. These dicts are reported to Dataroom as
JSON, and NaN is not valid JSON — ``None`` survives the round trip as null and
reads as "not measurable" instead of as a number.

AP is the primary metric. With a few hundred curated positives against many
more negatives, accuracy is uninformative (predicting "no" scores well) and
AUROC flatters a classifier that is wrong only on the rare class; average
precision is the one that moves when the head gets the positives right.
"""

import numpy as np
from sklearn.metrics import (
    average_precision_score,
    log_loss,
    precision_recall_curve,
    roc_auc_score,
)

PRIMARY = "ap"
SECONDARIES = ("auroc", "f1_best", "f1_at_0.5", "ece", "logloss", "recall_at_p90")
# Undefined without both classes present; None then.
TWO_CLASS_ONLY = ("ap", "auroc", "f1_best", "threshold_f1_best", "recall_at_p90")


def expected_calibration_error(scores: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> float:
    """How far predicted confidence sits from observed frequency, bin-weighted."""
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    index = np.clip(np.digitize(scores, bins[1:-1]), 0, n_bins - 1)
    ece = 0.0
    for bin_id in range(n_bins):
        mask = index == bin_id
        if mask.any():
            ece += mask.mean() * abs(scores[mask].mean() - labels[mask].mean())
    return float(ece)


def compute_metrics(scores, labels) -> dict[str, float | None]:
    """Every metric the trainer reports, from scores in [0,1] and hard labels."""
    scores = np.asarray(scores, dtype=np.float64).reshape(-1)
    labels = np.asarray(labels).astype(int).reshape(-1)
    n = len(labels)
    n_pos = int(labels.sum())
    out: dict[str, float | None] = {"n": float(n), "n_pos": float(n_pos)}
    if n == 0:
        return out

    predictions = (scores > 0.5).astype(int)
    true_pos = int(((predictions == 1) & (labels == 1)).sum())
    false_pos = int(((predictions == 1) & (labels == 0)).sum())
    false_neg = int(((predictions == 0) & (labels == 1)).sum())
    precision = true_pos / (true_pos + false_pos) if true_pos + false_pos else 0.0
    recall = true_pos / (true_pos + false_neg) if true_pos + false_neg else 0.0
    out["acc_at_0.5"] = float((predictions == labels).mean())
    out["precision_at_0.5"] = precision
    out["recall_at_0.5"] = recall
    out["f1_at_0.5"] = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    out["ece"] = expected_calibration_error(scores, labels)
    eps = 1e-7
    out["logloss"] = float(log_loss(labels, np.clip(scores, eps, 1 - eps), labels=[0, 1]))

    if not 0 < n_pos < n:
        out.update(dict.fromkeys(TWO_CLASS_ONLY))
        return out

    out["ap"] = float(average_precision_score(labels, scores))
    out["auroc"] = float(roc_auc_score(labels, scores))
    curve_precision, curve_recall, thresholds = precision_recall_curve(labels, scores)
    f1 = 2 * curve_precision * curve_recall / np.maximum(curve_precision + curve_recall, 1e-12)
    best = int(np.argmax(f1[:-1])) if len(thresholds) else 0
    out["f1_best"] = float(f1[best])
    out["threshold_f1_best"] = float(thresholds[best]) if len(thresholds) else 0.5
    # Recall reachable while holding precision at 90%.
    precise_enough = curve_precision[:-1] >= 0.9
    out["recall_at_p90"] = float(curve_recall[:-1][precise_enough].max()) if precise_enough.any() else 0.0
    return out
