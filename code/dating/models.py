"""The three dating models. Each is an sklearn Pipeline that takes the
DataFrame from data.model_input() (one 'text' column) and predicts a year.

1. tfidf_ridge   word TF-IDF (1-2 grams) + ridge regression.
                 What the manuscript is about: vocabulary and topics.
2. style_gbm     stylometric features (function word frequencies,
                 punctuation rates, word and sentence length) + gradient
                 boosting. How Peirce writes, mostly independent of topic.
3. hybrid_gbm    stylometric features + 100 latent topics (SVD of the word
                 TF-IDF) + gradient boosting. Style and content together, with
                 the content squeezed into a few dimensions.
"""
from sklearn.decomposition import TruncatedSVD
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import Ridge
from sklearn.pipeline import FeatureUnion, Pipeline
from sklearn.preprocessing import FunctionTransformer

from features import StyleFeatures, texts_of

RANDOM_STATE = 0


def word_tfidf():
    # sublinear_tf: log(1 + count), so long manuscripts do not dominate;
    # rows are L2-normalised, which removes the length effect further.
    return TfidfVectorizer(sublinear_tf=True, min_df=3, max_df=0.9,
                           ngram_range=(1, 2), max_features=100_000)


def gbm():
    # Absolute-error loss: robust to the few manuscripts with odd dates.
    return HistGradientBoostingRegressor(loss="absolute_error", learning_rate=0.05,
                                         max_iter=400, random_state=RANDOM_STATE)


def tfidf_ridge():
    return Pipeline([
        ("text", FunctionTransformer(texts_of)),
        ("tfidf", word_tfidf()),
        ("ridge", Ridge(alpha=0.05)),
    ])


def style_gbm():
    return Pipeline([
        ("style", StyleFeatures()),
        ("gbm", gbm()),
    ])


def hybrid_gbm():
    topics = Pipeline([
        ("text", FunctionTransformer(texts_of)),
        ("tfidf", word_tfidf()),
        ("svd", TruncatedSVD(n_components=100, random_state=RANDOM_STATE)),
    ])
    return Pipeline([
        ("features", FeatureUnion([("style", StyleFeatures()), ("topics", topics)])),
        ("gbm", gbm()),
    ])


MODELS = {"tfidf_ridge": tfidf_ridge, "style_gbm": style_gbm, "hybrid_gbm": hybrid_gbm}
