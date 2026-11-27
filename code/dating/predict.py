"""Estimate the year a Peirce manuscript was written, with a range.

Give one manuscript; get a point estimate and an 80% and a 95% interval.

    # a raw manuscript folder (with iiif/ and/or microfilm/ page files)
    python code/dating/predict.py data/manuscripts/MS-0001_hou02614c00003

    # a plain text file
    python code/dating/predict.py my_transcription.txt

    # a manuscript from manuscripts_dataset.csv, by folder name or Robin number
    python code/dating/predict.py --id MS-0001_hou02614c00003
    python code/dating/predict.py --id 1

    # all undated manuscripts at once -> results/undated_predictions.csv
    python code/dating/predict.py --undated

Options: --model tfidf_ridge|style_gbm|hybrid_gbm (default: the best model in
cross-validation, see models/best_model.txt), --all-models to show all three.

The models must be trained first: python code/dating/train_evaluate.py
"""
import argparse
import os
import sys

import joblib
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, ".."))
from clean_data import read_pages, remove_deleted, remove_tags  # noqa: E402
from data import load, model_input  # noqa: E402
from models import MODELS  # noqa: E402
from train_evaluate import MODEL_DIR, RESULTS, predict  # noqa: E402


def text_from_folder(path):
    """Same cleaning as clean_data.py, for one raw manuscript folder."""
    sources = {}
    for source in ("iiif", "microfilm"):
        d = os.path.join(path, source)
        pages = []
        if os.path.isdir(d):
            for page in read_pages(d):     # read_pages sorts and drops empty pages
                page = remove_tags(remove_deleted(page)).strip()
                if page:
                    pages.append(page)
        sources[source] = pages
    # Like clean_data.py: the source with most pages, iiif when equal.
    use = "iiif" if len(sources["iiif"]) >= len(sources["microfilm"]) and sources["iiif"] else "microfilm"
    return " ".join(" ".join(sources[use]).split()), use


def load_text(args):
    if args.id:
        df = load()
        key = args.id
        hit = df[(df["folder"] == key) | (df["robin"].astype(str) == key)]
        if hit.empty:
            sys.exit(f"No manuscript '{key}' in manuscripts_dataset.csv")
        row = hit.iloc[0]
        known = None
        if row["has_date"]:
            known = f"{row['date_low']:.0f}-{row['date_high']:.0f}"
        return row["text"], f"{row['folder']}  ({row['title']})", known
    path = args.path
    if os.path.isdir(path):
        text, source = text_from_folder(path)
        return text, f"{os.path.basename(os.path.normpath(path))}  (source: {source})", None
    with open(path, encoding="utf-8") as f:
        return " ".join(f.read().split()), os.path.basename(path), None


def load_model(name):
    path = os.path.join(MODEL_DIR, f"{name}.joblib")
    if not os.path.exists(path):
        sys.exit(f"{path} not found. Train first: python code/dating/train_evaluate.py")
    return joblib.load(path)


def best_model():
    path = os.path.join(MODEL_DIR, "best_model.txt")
    return open(path).read().strip() if os.path.exists(path) else "hybrid_gbm"


def run_undated(names):
    df = load()
    # Undated manuscripts (and dated ones the training left out because the
    # sources disagree by 4+ years), with text.
    todo = df[~df["train"] & (df["n_words"] > 0)].reset_index(drop=True)
    X = model_input(todo)
    out = todo[["folder", "robin", "title", "category", "n_words", "source_used",
                "has_date", "date_low", "date_high"]].copy()
    for name in names:
        p = predict(load_model(name), X)
        for col in p.columns:
            out[f"{name}_{col}"] = p[col].round(1).to_numpy()
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, "undated_predictions.csv")
    out.to_csv(path, index=False)
    print(f"{len(out)} manuscripts -> {path}")


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("path", nargs="?", help="manuscript folder or .txt file")
    parser.add_argument("--id", help="folder name or Robin number in manuscripts_dataset.csv")
    parser.add_argument("--undated", action="store_true", help="predict all undated manuscripts")
    parser.add_argument("--model", choices=list(MODELS), help="model to use")
    parser.add_argument("--all-models", action="store_true", help="show all three models")
    args = parser.parse_args()

    names = list(MODELS) if args.all_models else [args.model or best_model()]
    if args.undated:
        return run_undated(names)
    if not args.path and not args.id:
        parser.error("give a manuscript folder, a .txt file, --id or --undated")

    text, label, known = load_text(args)
    n_words = len(text.split())
    print(f"Manuscript: {label}")
    print(f"Words: {n_words}")
    if n_words < 300:
        print("Note: short text, the estimate is less reliable than the interval suggests "
              "(see results/cv_breakdown.csv).")
    X = model_input(pd.DataFrame({"text": [text]}))
    for name in names:
        p = predict(load_model(name), X).iloc[0]
        print(f"\n[{name}]")
        print(f"  estimate:      {p['pred']:.0f}")
        print(f"  80% interval:  {np.floor(p['lo80']):.0f} - {np.ceil(p['hi80']):.0f}")
        print(f"  95% interval:  {np.floor(p['lo95']):.0f} - {np.ceil(p['hi95']):.0f}")
    if known:
        print(f"\nCatalogue date: {known} (this manuscript was used in training, "
              "so the estimate is optimistic)")


if __name__ == "__main__":
    main()
