"""Train and compare the three dating models with grouped 5-fold CV.

Usage (from the repo root, after python code/clean_data.py):

    python code/dating/train_evaluate.py            # evaluate + fit final models
    python code/dating/train_evaluate.py --no-final # only the evaluation

What it does
------------
1. Loads the dated Peirce manuscripts (data.load): MS-* only, sources agree
   to within 4 years. Target = mean of the source midpoints.
2. Puts drafts of the same work in one group (features.draft_groups).
3. Outer loop: 5-fold GroupKFold. For every fold each model is wrapped in a
   MAPIE CrossConformalRegressor (CV+, itself with a grouped 5-fold split
   on the training part only), fitted on 4 folds, and asked for a point
   estimate plus 80% and 95% intervals on the held-out fold.
4. Writes metrics, out-of-fold predictions and plots to results/.
5. Fits every model once more on all dated data and saves it to models/,
   for predict.py.
"""
import argparse
import json
import os
import sys
import time

import joblib
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from mapie.regression import CrossConformalRegressor
from sklearn.decomposition import TruncatedSVD
from sklearn.model_selection import GroupKFold

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from data import load, model_input  # noqa: E402
from features import draft_groups  # noqa: E402
from models import MODELS, RANDOM_STATE  # noqa: E402

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..")
RESULTS = os.path.join(ROOT, "results")
MODEL_DIR = os.path.join(ROOT, "models")

K = 5
LEVELS = [0.80, 0.95]
YEAR_MIN, YEAR_MAX = 1850, 1914   # first writings ... Peirce's death


def conformal(name, groups_cv_seed=RANDOM_STATE):
    return CrossConformalRegressor(
        estimator=MODELS[name](), confidence_level=LEVELS, method="plus",
        cv=GroupKFold(n_splits=K, shuffle=True, random_state=groups_cv_seed),
    )


def predict(cp, X):
    point, intervals = cp.predict_interval(X)
    point = np.clip(point, YEAR_MIN, YEAR_MAX)
    out = {"pred": point}
    for j, level in enumerate(LEVELS):
        p = int(level * 100)
        out[f"lo{p}"] = np.clip(intervals[:, 0, j], YEAR_MIN, YEAR_MAX)
        out[f"hi{p}"] = np.clip(intervals[:, 1, j], YEAR_MIN, YEAR_MAX)
    return pd.DataFrame(out)


def metrics(y, p):
    err = p["pred"].to_numpy() - y
    row = {
        "MAE": np.abs(err).mean(),
        "median_AE": np.median(np.abs(err)),
        "RMSE": np.sqrt((err ** 2).mean()),
        "R2": 1 - (err ** 2).sum() / ((y - y.mean()) ** 2).sum(),
        "within_2y": (np.abs(err) <= 2).mean(),
        "within_5y": (np.abs(err) <= 5).mean(),
        "bias": err.mean(),
    }
    for level in LEVELS:
        q = int(level * 100)
        if f"lo{q}" in p:
            row[f"coverage_{q}"] = ((y >= p[f"lo{q}"]) & (y <= p[f"hi{q}"])).mean()
            row[f"width_{q}"] = (p[f"hi{q}"] - p[f"lo{q}"]).mean()
    return row


def shrink_for_saving(obj, seen=None):
    """Store the SVD topic matrices of hybrid_gbm as float32 instead of
    float64: halves the file (~470 -> ~240 MB). Estimates move by well under
    a year, far inside the CV error."""
    seen = set() if seen is None else seen
    if id(obj) in seen:
        return
    seen.add(id(obj))
    if isinstance(obj, TruncatedSVD) and hasattr(obj, "components_"):
        obj.components_ = obj.components_.astype(np.float32)
    if isinstance(obj, (list, tuple)):
        children = obj
    elif isinstance(obj, dict):
        children = obj.values()
    elif hasattr(obj, "__dict__") and type(obj).__module__.split(".")[0] in ("sklearn", "mapie"):
        children = vars(obj).values()
    else:
        return
    for child in children:
        shrink_for_saving(child, seen)


def evaluate(df, X, y, groups):
    outer = GroupKFold(n_splits=K, shuffle=True, random_state=RANDOM_STATE)
    folds = np.zeros(len(y), dtype=int)
    preds = {}
    for name in MODELS:
        parts = []
        t0 = time.time()
        for f, (tr, te) in enumerate(outer.split(X, y, groups)):
            folds[te] = f
            cp = conformal(name).fit_conformalize(X.iloc[tr], y[tr], groups=groups[tr])
            p = predict(cp, X.iloc[te])
            p.index = te
            parts.append(p)
            print(f"  {name} fold {f + 1}/{K} done ({time.time() - t0:.0f}s)", flush=True)
        preds[name] = pd.concat(parts).sort_index()

    # Baseline from the proposal: always the median year of the training folds.
    base = np.zeros(len(y))
    for tr, te in outer.split(X, y, groups):
        base[te] = np.median(y[tr])
    preds["baseline_median"] = pd.DataFrame({"pred": base})
    return preds, folds


def breakdowns(df, y, preds):
    """MAE (and 80% coverage) per period, text length and transcription source."""
    cuts = {
        "period": pd.cut(y, [1849, 1870, 1880, 1890, 1900, 1910, 1915],
                         labels=["1850-1870", "1871-1880", "1881-1890",
                                 "1891-1900", "1901-1910", "1911-1914"]),
        "length": pd.cut(df["n_words"], [0, 300, 1000, 5000, np.inf],
                         labels=["<300 words", "300-1000", "1000-5000", ">5000"]),
        "source": df["source_used"],
    }
    rows = []
    for by, key in cuts.items():
        for level in pd.Series(key).dropna().unique():
            m = (np.asarray(key) == level)
            for name, p in preds.items():
                r = {"by": by, "group": level, "n": int(m.sum()), "model": name,
                     "MAE": np.abs(p["pred"].to_numpy()[m] - y[m]).mean()}
                if "lo80" in p:
                    r["coverage_80"] = ((y[m] >= p["lo80"].to_numpy()[m]) &
                                        (y[m] <= p["hi80"].to_numpy()[m])).mean()
                    r["width_80"] = (p["hi80"] - p["lo80"]).to_numpy()[m].mean()
                rows.append(r)
    return pd.DataFrame(rows).sort_values(["by", "group", "model"])


def plots(y, preds):
    names = list(MODELS)
    fig, axes = plt.subplots(1, len(names), figsize=(5 * len(names), 5), sharey=True)
    for ax, name in zip(axes, names):
        p = preds[name]
        ax.errorbar(y, p["pred"], yerr=[p["pred"] - p["lo80"], p["hi80"] - p["pred"]],
                    fmt="o", ms=3, alpha=0.35, elinewidth=0.5, color="#2a6f97")
        ax.plot([1850, 1914], [1850, 1914], color="#c44536", lw=1)
        mae = np.abs(p["pred"] - y).mean()
        ax.set_title(f"{name} (MAE {mae:.1f} y)")
        ax.set_xlabel("catalogue date (target)")
    axes[0].set_ylabel("predicted year (bars: 80% interval)")
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "predicted_vs_actual.png"), dpi=120)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    bins = np.arange(0, 31, 1)
    for name in names:
        ax.hist(np.abs(preds[name]["pred"] - y), bins=bins, histtype="step", lw=1.5, label=name)
    ax.hist(np.abs(preds["baseline_median"]["pred"] - y), bins=bins, histtype="step",
            lw=1, ls="--", color="grey", label="baseline_median")
    ax.set_xlabel("absolute error (years)")
    ax.set_ylabel("manuscripts")
    ax.legend()
    fig.tight_layout()
    fig.savefig(os.path.join(RESULTS, "error_distribution.png"), dpi=120)
    plt.close(fig)


def expert_disagreement(df):
    """Mean |Irvine - Houghton| midpoint where both exist: the human benchmark."""
    both = df[["irvine_mid", "houghton_mid"]].dropna()
    return float((both["irvine_mid"] - both["houghton_mid"]).abs().mean()), len(both)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-final", action="store_true", help="skip fitting the final models")
    args = parser.parse_args()
    os.makedirs(RESULTS, exist_ok=True)

    df_all = load()
    df = df_all[df_all["train"]].reset_index(drop=True)
    X, y = model_input(df), df["target"].to_numpy()
    groups = draft_groups(df)
    print(f"{len(df)} dated manuscripts, {len(set(groups))} draft groups "
          f"(largest {np.bincount(groups).max()})")

    preds, folds = evaluate(df, X, y, groups)

    table = pd.DataFrame({name: metrics(y, p) for name, p in preds.items()}).T
    table.index.name = "model"
    table.to_csv(os.path.join(RESULTS, "cv_metrics.csv"), float_format="%.3f")
    print(table.round(3).to_string())

    out = df[["folder", "robin", "title", "category", "n_words", "source_used",
              "date_low", "date_high", "target"]].copy()
    out["group"], out["fold"] = groups, folds
    for name, p in preds.items():
        for col in p.columns:
            out[f"{name}_{col}"] = p[col].to_numpy()
    out.to_csv(os.path.join(RESULTS, "cv_predictions.csv"), index=False, float_format="%.2f")

    br = breakdowns(df, y, preds)
    br.to_csv(os.path.join(RESULTS, "cv_breakdown.csv"), index=False, float_format="%.3f")
    plots(y, preds)

    disagreement, n_both = expert_disagreement(df_all[df_all["has_date"]])
    best = table.drop(index="baseline_median")["MAE"].idxmin()
    summary = {"n_train": len(df), "n_groups": int(len(set(groups))), "k": K,
               "expert_disagreement_mae": disagreement, "n_with_two_sources": n_both,
               "best_model": best}
    with open(os.path.join(RESULTS, "summary.json"), "w") as f:
        json.dump(summary, f, indent=2)
    print(summary)

    if args.no_final:
        return
    os.makedirs(MODEL_DIR, exist_ok=True)
    for name in MODELS:
        t0 = time.time()
        cp = conformal(name).fit_conformalize(X, y, groups=groups)
        shrink_for_saving(cp)
        joblib.dump(cp, os.path.join(MODEL_DIR, f"{name}.joblib"), compress=3)
        print(f"final {name} saved ({time.time() - t0:.0f}s)")
    with open(os.path.join(MODEL_DIR, "best_model.txt"), "w") as f:
        f.write(best + "\n")
    # Saved models only load with the same library versions.
    import mapie, sklearn
    with open(os.path.join(MODEL_DIR, "versions.txt"), "w") as f:
        f.write(f"python {sys.version.split()[0]}\nscikit-learn {sklearn.__version__}\n"
                f"mapie {mapie.__version__}\nnumpy {np.__version__}\npandas {pd.__version__}\n")


if __name__ == "__main__":
    main()
