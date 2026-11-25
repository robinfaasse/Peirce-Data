"""Load manuscripts_dataset.csv and build the modelling target."""
import os
import sys

import numpy as np
import pandas as pd

from features import preprocess

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from clean_data import FOLDER as DATA  # noqa: E402  (data/ or Data/peirce_transcriptions/)
SOURCES = ["irvine", "houghton", "robin"]

# Training uses manuscripts whose sources agree to within this many years
# (latest end minus earliest start < MAX_SPAN), as in the proposal.
MAX_SPAN = 4


def load(folder=DATA):
    """All Peirce manuscripts (MS-*, letters L-* are left out) with target info.

    Columns added:
      target       mean of the midpoints of the available date sources
      date_low     earliest start over all sources
      date_high    latest end over all sources
      span         date_high - date_low (expert disagreement / own range)
      source_used  iiif or microfilm (which transcription the text comes from)
      train        True when the manuscript is used for training
    """
    df = pd.read_csv(os.path.join(folder, "manuscripts_dataset.csv"), encoding="utf-8-sig")
    overview = pd.read_csv(os.path.join(folder, "manuscripts_combined_overview.csv"))
    df = df.merge(overview[["folder", "source_used"]], on="folder", how="left")

    df = df[df["folder"].str.startswith("MS")].reset_index(drop=True)
    df["text"] = df["text"].fillna("")
    df["target"] = df[[f"{s}_mid" for s in SOURCES]].mean(axis=1)
    df["date_low"] = df[[f"{s}_start" for s in SOURCES]].min(axis=1)
    df["date_high"] = df[[f"{s}_end" for s in SOURCES]].max(axis=1)
    df["span"] = df["date_high"] - df["date_low"]
    df["train"] = df["has_date"] & (df["span"] < MAX_SPAN) & (df["n_words"] > 0)
    return df


def model_input(df):
    """The X that every model takes: a DataFrame with the cleaned text."""
    return pd.DataFrame({"text": [preprocess(t) for t in df["text"]]})
