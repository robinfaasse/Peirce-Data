"""Text preprocessing, stylometric features and draft grouping.

Shared by train_evaluate.py and predict.py so a new manuscript goes through
exactly the same steps as the training data.
"""
import re

import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import connected_components
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer

# Longest text used, in words. A few manuscripts have >100k words; the first
# MAX_WORDS are plenty for both TF-IDF and the style frequencies and keep
# training fast.
MAX_WORDS = 30000

# Years Peirce wrote in the text ("1903") would let the model read off the
# date. Catalogue dates were often based on exactly those years, and an
# undated manuscript rarely has one, so cross-validation would look better
# than real use. All 4-digit numbers 1800-1929 become the token "yearnum".
YEAR_PATTERN = re.compile(r"\b1[89]\d\d\b|\b19[0-2]\d\b")


def preprocess(text):
    """Clean text the same way for training and prediction."""
    if not isinstance(text, str):
        return ""
    words = text.split()
    if len(words) > MAX_WORDS:
        text = " ".join(words[:MAX_WORDS])
    return YEAR_PATTERN.sub(" yearnum ", text)


# --------------------------------------------------------------------------
# Stylometric features
# --------------------------------------------------------------------------

# Function words: frequent, topic-independent. The relative frequencies of
# these say something about style (and its change over time) rather than about
# the subject of the manuscript.
FUNCTION_WORDS = """
a about above after again against all almost along already also although always
am among an and another any anything are around as at be because been before
being below between both but by can cannot could did do does doing done down
during each either enough even ever every few for from further had has have
having he hence her here hers herself him himself his how however i if in
indeed into is it its itself just least less let like may me might more most
much must my myself neither never no nor not nothing now of off often on once
one only or other others otherwise ought our ours ourselves out over own per
perhaps quite rather same shall she should since so some something still such
than that the their theirs them themselves then thence there therefore these
they this those though through thus to together too toward towards under unless
until up upon us very was we were what whatever when whence where whereas
whether which while who whoever whole whom whose why will with within without
would yet you your yours yourself
""".split()

PUNCTUATION = {
    "comma": ",", "semicolon": ";", "colon": ":", "period": ".", "question": "?",
    "exclamation": "!", "dash": "-", "emdash": "—", "paren": "(",
    "dquote": '"', "squote": "'", "ampersand": "&",
}

WORD_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?")
SENT_RE = re.compile(r"[.!?]+")


def style_vector(text):
    """Length-independent style measures of one text (all rates or averages)."""
    words = WORD_RE.findall(text)
    lower = [w.lower() for w in words]
    n_words = max(len(words), 1)
    n_chars = max(len(text), 1)

    counts = pd.Series(lower).value_counts() if lower else pd.Series(dtype=int)
    feats = {f"fw_{w}": counts.get(w, 0) / n_words for w in FUNCTION_WORDS}
    for name, ch in PUNCTUATION.items():
        feats[f"punct_{name}"] = text.count(ch) / n_chars * 1000
    lengths = np.array([len(w) for w in words]) if words else np.array([0])
    n_sent = max(len(SENT_RE.findall(text)), 1)
    first = lower[:1000]
    feats.update({
        "mean_word_len": lengths.mean(),
        "long_word_share": (lengths >= 8).mean(),
        "mean_sentence_len": n_words / n_sent,
        "type_token_1000": len(set(first)) / max(len(first), 1),  # fixed window
        "capital_share": sum(w[0].isupper() for w in words) / n_words,
        "digit_rate": sum(c.isdigit() for c in text) / n_chars * 1000,
        "function_word_share": sum(counts.get(w, 0) for w in FUNCTION_WORDS) / n_words,
        "log_n_words": np.log1p(len(words)),
    })
    return feats


_STYLE_CACHE = {}


def _cached_style(text):
    # Cross-validation computes the same texts many times; cache per text.
    key = hash(text)
    if key not in _STYLE_CACHE:
        _STYLE_CACHE[key] = style_vector(text)
    return _STYLE_CACHE[key]


class StyleFeatures(BaseEstimator, TransformerMixin):
    """sklearn transformer: texts -> dense stylometric matrix."""

    def fit(self, X, y=None):
        return self

    def transform(self, X):
        rows = [_cached_style(t) for t in texts_of(X)]
        return pd.DataFrame(rows).to_numpy(dtype=float)

    def get_feature_names_out(self, input_features=None):
        return np.array(list(style_vector("a").keys()))


def texts_of(X):
    """Accept a DataFrame with a 'text' column, a Series or a list."""
    if isinstance(X, pd.DataFrame):
        return X["text"].tolist()
    return list(np.asarray(X).ravel())


# --------------------------------------------------------------------------
# Grouping drafts of the same work
# --------------------------------------------------------------------------

def _norm_title(title):
    t = str(title).lower()
    t = re.sub(r"\[|\]|\(.*?\)", " ", t)
    t = re.sub(r"[^a-z ]", " ", t)
    return " ".join(t.split())


GENERIC_TITLES = {"", "fragments", "miscellaneous fragments", "fragment", "notes",
                  "diary", "preface", "untitled", "logic", "pragmatism"}


def draft_groups(df, sim_threshold=0.5, robin_window=10):
    """Give every manuscript a group id; drafts of one work share an id.

    Two manuscripts are linked when
      1. they share the base Robin number (427, 427a, 427b), or
      2. they have the same (non-generic) title and Robin numbers at most
         `robin_window` apart (Robin numbered drafts consecutively), or
      3. their texts are very similar: TF-IDF cosine similarity > sim_threshold.
    Groups are the connected components of these links, so a chain of drafts
    ends up together. Cross-validation folds never split a group.
    """
    n = len(df)
    rows, cols = [], []

    base = df["robin"].astype(str).str.extract(r"^(\d+)")[0]
    num = pd.to_numeric(base, errors="coerce").to_numpy()
    for key, idx in pd.Series(range(n)).groupby(base.to_numpy()).groups.items():
        idx = list(idx)
        rows += idx[:-1]
        cols += idx[1:]

    titles = df["title"].map(_norm_title).to_numpy()
    for key, idx in pd.Series(range(n)).groupby(titles).groups.items():
        if key in GENERIC_TITLES:
            continue
        idx = list(idx)
        for a in idx:
            for b in idx:
                if a < b and abs(num[a] - num[b]) <= robin_window:
                    rows.append(a)
                    cols.append(b)

    texts = [preprocess(t) for t in df["text"]]
    X = TfidfVectorizer(sublinear_tf=True, min_df=2, max_df=0.5,
                        stop_words="english").fit_transform(texts)
    S = (X @ X.T).tocoo()
    mask = (S.data > sim_threshold) & (S.row < S.col)
    rows += S.row[mask].tolist()
    cols += S.col[mask].tolist()

    A = csr_matrix((np.ones(len(rows)), (rows, cols)), shape=(n, n))
    _, labels = connected_components(A, directed=False)
    return labels
