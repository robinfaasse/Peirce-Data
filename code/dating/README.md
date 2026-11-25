# Dating models

Three models that estimate the year a Peirce manuscript was written, each
with an 80% and a 95% prediction interval (conformal prediction, MAPIE).

## Run

```
pip install -r requirements.txt
python code/clean_data.py                      # makes data/manuscripts_dataset.csv
python code/dating/train_evaluate.py           # ~20 min: CV comparison + final models in models/ (~500 MB, not in git)
python code/dating/predict.py data/manuscripts/MS-0001_hou02614c00003
python code/dating/predict.py --id 1 --all-models
python code/dating/predict.py --undated        # all undated -> results/undated_predictions.csv
python code/dating/app.py                      # web page on http://localhost:8000
```

### Web page

`app.py` starts a small local server (standard library only) that loads the
three trained models once and serves `static/index.html`. On the page you can
paste text, upload one or more `.txt` pages, or pick a raw manuscript folder
(with `iiif/` and/or `microfilm/`). Uploads get the same cleaning as
`clean_data.py`. It shows each model's estimate, 80% and 95% range on a
timeline, with the CV scores of each model and warnings for short or early
texts. It runs on your own computer; nothing is sent anywhere else.
Train first (`train_evaluate.py`), since the page uses `models/*.joblib`.

`predict.py` takes a raw manuscript folder (it applies the same cleaning as
`clean_data.py`), a plain `.txt` file, or a manuscript id from the dataset.
Example output:

```
[hybrid_gbm]
  estimate:      1902
  80% interval:  1892 - 1912
  95% interval:  1884 - 1914
```

## Design choices

**Training data.** Manuscripts by Peirce (`MS-*`; the letters `L-*` are left
out, as in the proposal) that have a date and whose sources agree: latest end
minus earliest start over Irvine, Houghton and Robin is under 4 years. That
leaves 914 manuscripts (the proposal estimated 916).

**Target.** The mean of the midpoints of the available sources. With one
source and a range "1890-1894" that is 1892; with Irvine 1904 and Houghton
1903 it is 1903.5. No source is preferred over another.

**Drafts stay together.** Peirce wrote many drafts of one text. Two
manuscripts are put in the same group when they share a base Robin number
(427, 427a, 427b), have the same non-generic title with Robin numbers at most
10 apart, or have a TF-IDF cosine similarity above 0.5. The 914 manuscripts
form 776 groups (largest: 7). Every split (outer CV and the conformal inner
CV) is a `GroupKFold`, so a group is never in train and test at once.

**Years in the text are masked.** Any 1800-1929 number in the text becomes
`yearnum`. Cataloguers often dated a manuscript from a year Peirce wrote in
it, and undated manuscripts rarely have one, so leaving them in would make
CV look better than real use.

**Length and OCR.** Texts are capped at the first 30,000 words. TF-IDF uses
`sublinear_tf` and L2-normalised rows, and all style features are rates
(per word or per 1000 characters), so length is not a feature by accident
(`log_n_words` is included explicitly). Results are broken down by length and
by source (iiif vs. microfilm) below.

## The three models

| model | features | learner | idea |
|---|---|---|---|
| `tfidf_ridge` | word TF-IDF, 1-2 grams, 100k terms | ridge regression | what the text is about |
| `style_gbm` | 189 function-word frequencies, 12 punctuation rates, word/sentence length, type-token ratio, capitals, digits | gradient boosting | how Peirce writes, topic-free |
| `hybrid_gbm` | style features + 100 SVD topics of the TF-IDF | gradient boosting | both, content compressed |

Gradient boosting uses absolute-error loss (robust to odd dates). Intervals
come from MAPIE `CrossConformalRegressor` (CV+, grouped 5 folds). Predictions
and intervals are clipped to 1850-1914.

## Results (grouped 5-fold CV, 914 manuscripts)

| model | MAE | median AE | within 2 y | within 5 y | R² | 80% coverage | 80% width | 95% coverage | 95% width |
|---|---|---|---|---|---|---|---|---|---|
| baseline (median year) | 9.78 | 6.63 | 12% | 39% | -0.04 | | | | |
| tfidf_ridge | 6.22 | 4.37 | 26% | 55% | 0.58 | 80% | 20.1 | 95% | 33.2 |
| style_gbm | 6.60 | 4.49 | 26% | 55% | 0.48 | 82% | 21.4 | 96% | 37.0 |
| **hybrid_gbm** | **5.76** | **3.50** | **33%** | **61%** | 0.56 | 83% | 19.4 | 97% | 35.6 |

Expert disagreement for reference: where Irvine and Houghton both date a
manuscript (341 cases), their midpoints differ by 0.75 years on average.

Full numbers: `results/cv_metrics.csv`, per manuscript `results/cv_predictions.csv`,
per period/length/source `results/cv_breakdown.csv`, plots
`results/predicted_vs_actual.png` and `results/error_distribution.png`.

## What the results say

- All three clearly beat the baseline; `hybrid_gbm` is best and is the
  default in `predict.py`. They are far from the experts (0.75 years).
- **Style alone almost matches content** (6.6 vs 6.2 years MAE). So the
  models do pick up real change in how Peirce writes, not only topic.
- **Regression to the middle.** 1891-1910 (650 of 914 manuscripts) has an
  MAE of about 3 years; before 1880 the error is 13-19 years and predictions
  are pulled towards the 1890s. Early manuscripts are few in training.
- **Coverage is right on average but not per period.** The interval has the
  same width (~20 years at 80%) for every manuscript. It covers 95%+ in
  1891-1910 and only ~20% before 1880. Same for length: below 300 words
  coverage drops to 54-73%. `predict.py` warns for short texts.
- **Microfilm is harder than iiif** (MAE 6.2 vs 4.0 for `hybrid_gbm`), in
  line with the worse OCR, though the microfilm set also has more early
  manuscripts.

## Next steps

- Make intervals adaptive: conformal per length or period bin (Mondrian),
  or conformalized quantile regression (MAPIE `ConformalizedQuantileRegressor`),
  so short or early-looking texts get wider ranges.
- Reduce regression to the middle: sample weights by period, or a
  classification-then-regression set-up.
- Sentence embeddings (SBERT) as a fourth feature set, as the supervisor
  suggested.
- Predict the undated manuscripts: `predict.py --undated` already writes
  `results/undated_predictions.csv`.
