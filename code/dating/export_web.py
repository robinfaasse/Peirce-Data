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


def dataset_stats():
    """Numbers and distributions for the Dataset tab of the page."""
    from data import DATA, load as load_data
    index = pd.read_csv(os.path.join(DATA, "index.csv"))
    overview = pd.read_csv(os.path.join(DATA, "manuscripts_combined_overview.csv"))
    df = load_data()
    train, undated = df[df["train"]], df[~df["has_date"]]
    excluded = df[df["has_date"] & ~df["train"]]
    n_pages = int(overview["iiif_pages_with_text"].sum() + overview["microfilm_pages_with_text"].sum())

    def by(frame, col, keys):
        counts = frame[col].value_counts()
        return [int(counts.get(k, 0)) for k in keys]

    years = list(range(1850, 1915))
    year_counts = np.floor(train["target"]).astype(int).value_counts()
    edges = [0, 100, 300, 1000, 3000, 10000, 30000, np.inf]
    labels = ["<100", "100-300", "300-1k", "1k-3k", "3k-10k", "10k-30k", ">30k"]
    lengths = lambda f: pd.cut(f["n_words"], edges, labels=labels, right=False).value_counts()
    cats = df["category"].value_counts().index.tolist()
    spans = train["span"].value_counts()
    sources = ["irvine", "houghton", "robin"]
    return {
        "funnel": [
            {"label": "Catalogue records", "n": int(len(index)), "note": "index.csv: every record of MS Am 1632"},
            {"label": "With a transcription folder", "n": int(index["package_path"].notna().sum()), "note": "the rest were never transcribed"},
            {"label": "With text after cleaning", "n": int((overview["n_words"] > 0).sum()), "note": "folders with only blank pages dropped"},
            {"label": "Written by Peirce (MS)", "n": int(len(df)), "note": "letters (L-) left out"},
            {"label": "With a date", "n": int(df["has_date"].sum()), "note": "dated by Irvine, Houghton or Robin"},
            {"label": "Sources agree within 4 years", "n": int(len(train)), "note": "the training set"},
        ],
        "undated": int(len(undated)), "excluded_span": int(len(excluded)),
        "letters": int((overview["folder"].str.startswith("L") & (overview["n_words"] > 0)).sum()),
        "n_pages": n_pages, "n_words": int(df["n_words"].sum()),
        "median_words_train": int(train["n_words"].median()),
        "median_words_undated": int(undated["n_words"].median()),
        "years": years, "year_counts": [int(year_counts.get(y, 0)) for y in years],
        "median_year": float(train["target"].median()),
        "length_labels": labels,
        "length_train": [int(lengths(train)[l]) for l in labels],
        "length_undated": [int(lengths(undated)[l]) for l in labels],
        "categories": [c.split(". ", 1)[-1] for c in cats],
        "category_train": by(train, "category", cats), "category_undated": by(undated, "category", cats),
        "source_train": by(train, "source_used", ["iiif", "microfilm"]),
        "source_undated": by(undated, "source_used", ["iiif", "microfilm"]),
        "date_sources": {s: int(train[f"{s}_mid"].notna().sum()) for s in sources},
        "two_sources": int((train[[f"{s}_mid" for s in sources]].notna().sum(axis=1) >= 2).sum()),
        "span_counts": [int(spans.get(k, 0)) for k in range(4)],
    }


def all_manuscripts():
    """Every Peirce manuscript with its catalogue date, the three models'
    estimates and a 2D map of the features, for the All manuscripts tab.

    Dated training manuscripts get their out-of-fold CV estimate (the model
    never saw them); the others get the final models' estimate with CV+ 80%
    range. The map is t-SNE on the hybrid model's features (style +
    100 topics, standardised, reduced to 50 dimensions with PCA first)."""
    from sklearn.decomposition import PCA
    from sklearn.manifold import TSNE
    from sklearn.preprocessing import StandardScaler

    from data import load as load_data, model_input
    from train_evaluate import predict as mapie_predict

    df = load_data()
    df = df[df["n_words"] > 0].reset_index(drop=True)
    X = model_input(df)
    oof = pd.read_csv(os.path.join(RESULTS, "cv_predictions.csv")).set_index("folder")

    preds = {}
    for name in ("tfidf_ridge", "style_gbm", "hybrid_gbm"):
        mapie = joblib.load(os.path.join(MODEL_DIR, f"{name}.joblib"))
        p = mapie_predict(mapie, X)
        cols = {"pred": f"{name}_pred", "lo80": f"{name}_lo80", "hi80": f"{name}_hi80"}
        for key, col in cols.items():
            from_cv = df["folder"].map(oof[col]) if col in oof else None
            values = p[key].to_numpy()
            if from_cv is not None:
                values = np.where(from_cv.notna(), from_cv, values)
            preds[(name, key)] = values
        print(f"predicted {name}")

    hybrid = load("hybrid_gbm").estimator_.single_estimator_
    Z = hybrid.named_steps["features"].transform(X)
    Z = StandardScaler().fit_transform(Z)
    Z = PCA(n_components=50, random_state=0).fit_transform(Z)
    xy = TSNE(n_components=2, perplexity=30, init="pca", random_state=0).fit_transform(Z)

    rows = []
    for i, r in df.iterrows():
        row = {
            "id": r["folder"], "robin": str(r["robin"]), "title": str(r["title"]),
            "cat": str(r["category"]).split(". ", 1)[-1], "words": int(r["n_words"]),
            "src": r["source_used"], "dated": bool(r["has_date"]), "train": bool(r["train"]),
            "xy": [round(float(xy[i, 0]), 2), round(float(xy[i, 1]), 2)],
            "m": {name: [round(float(preds[(name, k)][i]), 1) for k in ("pred", "lo80", "hi80")]
                  for name in ("tfidf_ridge", "style_gbm", "hybrid_gbm")},
        }
        if r["has_date"]:
            row["date"] = [round(float(r["target"]), 1), int(r["date_low"]), int(r["date_high"])]
        rows.append(row)
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "manuscripts.json"), "w", encoding="utf-8") as f:
        json.dump(all_manuscripts(), f, ensure_ascii=False, separators=(",", ":"))
    with open(os.path.join(OUT, "dataset.json"), "w") as f:
        json.dump(dataset_stats(), f, indent=1)
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
