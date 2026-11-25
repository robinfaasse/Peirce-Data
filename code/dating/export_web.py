"""Export the trained models to docs/ so the page runs in any browser.

    python code/dating/export_web.py

Writes docs/model/: the shared TF-IDF vocabulary and idf, the ridge
coefficients, the SVD topic matrix (float16), both gradient-boosting
ensembles as plain arrays, and the conformal interval half-widths.
docs/index.html then does everything in JavaScript: no server, no Python.

Differences from predict.py, all small:
  - the point estimate comes from the model fitted on all 914 manuscripts
    (MAPIE's single_estimator_) instead of the mean of the 5 fold models;
  - the range is estimate +/- the conformal quantile of the out-of-fold
    absolute residuals (MAPIE's "base" cross-conformal method) instead of CV+;
  - the SVD matrix is stored as float16 (estimates move by ~0.02 years).
"""
import json
import math
import os
import sys

import joblib
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from features import FUNCTION_WORDS, MAX_WORDS, PUNCTUATION, style_vector  # noqa: E402
from train_evaluate import LEVELS, MODEL_DIR, RESULTS  # noqa: E402

OUT = os.path.join(HERE, "..", "..", "docs", "model")


def load(name):
    return joblib.load(os.path.join(MODEL_DIR, f"{name}.joblib"))._mapie_regressor


def half_widths(mapie):
    """Conformal quantile of the out-of-fold absolute residuals, per level."""
    s = np.sort(mapie.conformity_scores_[~np.isnan(mapie.conformity_scores_)])
    n = len(s)
    out = {}
    for level in LEVELS:
        q = min(math.ceil((n + 1) * level) / n, 1.0)
        out[str(int(level * 100))] = float(np.quantile(s, q, method="higher"))
    return out


def export_gbm(gbm):
    """All trees of a HistGradientBoostingRegressor as flat arrays."""
    trees = []
    for (pred,) in gbm._predictors:
        n = pred.nodes
        trees.append({
            "f": n["feature_idx"].tolist(),
            "t": [float(x) for x in n["num_threshold"]],
            "l": n["left"].tolist(),
            "r": n["right"].tolist(),
            "leaf": n["is_leaf"].astype(int).tolist(),
            "v": [round(float(x), 6) for x in n["value"]],
        })
    return {"baseline": float(np.ravel(gbm._baseline_prediction)[0]), "trees": trees}


def main():
    os.makedirs(OUT, exist_ok=True)
    ridge_m, style_m, hybrid_m = load("tfidf_ridge"), load("style_gbm"), load("hybrid_gbm")
    ridge = ridge_m.estimator_.single_estimator_
    style = style_m.estimator_.single_estimator_
    hybrid = hybrid_m.estimator_.single_estimator_

    tfidf = ridge.named_steps["tfidf"]
    topics = hybrid.named_steps["features"].transformer_list[1][1]
    assert tfidf.vocabulary_ == topics.named_steps["tfidf"].vocabulary_, "vocabularies differ"

    vocab = sorted(tfidf.vocabulary_, key=tfidf.vocabulary_.get)
    with open(os.path.join(OUT, "vocab.json"), "w", encoding="utf-8") as f:
        json.dump(vocab, f, ensure_ascii=False, separators=(",", ":"))
    tfidf.idf_.astype("<f4").tofile(os.path.join(OUT, "idf.f32"))
    ridge.named_steps["ridge"].coef_.astype("<f4").tofile(os.path.join(OUT, "ridge_coef.f32"))
    svd = topics.named_steps["svd"]
    svd.components_.astype("<f2").tofile(os.path.join(OUT, "svd.f16"))

    for name, model in (("style_gbm", style), ("hybrid_gbm", hybrid)):
        with open(os.path.join(OUT, f"{name}.json"), "w") as f:
            json.dump(export_gbm(model.named_steps["gbm"]), f, separators=(",", ":"))

    metrics = pd.read_csv(os.path.join(RESULTS, "cv_metrics.csv"), index_col="model")
    meta = {
        "max_words": MAX_WORDS,
        "function_words": FUNCTION_WORDS,
        "punctuation": PUNCTUATION,
        "style_names": list(style_vector("a").keys()),
        "n_vocab": len(vocab),
        "n_topics": int(svd.components_.shape[0]),
        "ridge_intercept": float(ridge.named_steps["ridge"].intercept_),
        "half_widths": {"tfidf_ridge": half_widths(ridge_m), "style_gbm": half_widths(style_m),
                        "hybrid_gbm": half_widths(hybrid_m)},
        "cv": {m: {k: round(float(v), 3) for k, v in metrics.loc[m].items() if pd.notna(v)}
               for m in metrics.index},
        "best": open(os.path.join(MODEL_DIR, "best_model.txt")).read().strip(),
    }
    with open(os.path.join(OUT, "meta.json"), "w") as f:
        json.dump(meta, f, indent=1)
    for name in sorted(os.listdir(OUT)):
        print(f"{name:20s} {os.path.getsize(os.path.join(OUT, name)) / 1e6:6.1f} MB")
    print(json.dumps(meta["half_widths"]))


if __name__ == "__main__":
    main()
