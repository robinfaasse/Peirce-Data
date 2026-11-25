"""Link every manuscript's combined text to its dates in index_correct_dates.csv.

Input:  Data/peirce_transcriptions/index_correct_dates.csv  (output of correct_date.py)
        Data/manuscripts_combined/*.txt                     (output of combine_pages.py)
Output: Data/manuscripts_dataset.csv

One row per manuscript: all columns of index_correct_dates.csv (metadata plus
the irvine_*, houghton_* and robin_* date columns), then
  has_date  True if at least one source gives a date
  n_words   number of words in the text
  text      the whole text of the manuscript in one cell
Only manuscripts with (non-empty) text are kept.

Link key: the folder name. package_path is "manuscripts/MS-0001_hou02614c00003",
and combine_pages.py saved that manuscript as "MS-0001_hou02614c00003.txt".
"""
import os

import pandas as pd

FOLDER = "/Users/robinfaasse/Documents/School/RUG - 2026:2027/Sem 1 - Block 1 + 2/Minor Data Wise/Collaborative Data Project/Data/peirce_transcriptions"
INDEX_FILE = os.path.join(FOLDER, "index_correct_dates.csv")
TEXT_DIR = os.path.join(FOLDER, "manuscripts_combined")
OUTPUT_FILE = os.path.join(FOLDER, "manuscripts_dataset.csv")
SOURCES = ["irvine", "houghton", "robin"]

# 1. Metadata and dates: one row per catalogue record.
index = pd.read_csv(INDEX_FILE, dtype={"robin": str, "houghton_id": str,
                                       **{f"{s}_dates": str for s in SOURCES},
                                       **{f"{s}_{c}": "Int64" for s in SOURCES
                                          for c in ("start", "end", "n")}})
index["package_path"] = index["package_path"].fillna("")
index["folder"] = index["package_path"].apply(lambda p: os.path.basename(p) if p else "")

# 2. Texts: one row per combined .txt file.
texts = []
for name in os.listdir(TEXT_DIR):
    if name.endswith(".txt"):
        with open(os.path.join(TEXT_DIR, name), encoding="utf-8") as f:
            texts.append({"folder": name[:-4], "text": f.read().strip()})
texts = pd.DataFrame(texts, columns=["folder", "text"])

# 3. Link: keep manuscripts that have both a row in the index and text.
data = index[index["folder"] != ""].merge(texts, on="folder", how="inner", validate="one_to_one")
data = data[data["text"] != ""]

# 4. Extra columns; the text goes last.
data["has_date"] = data[[f"{s}_start" for s in SOURCES]].notna().any(axis=1)
data["n_words"] = data["text"].str.split().str.len()
data = data[[c for c in data.columns if c != "text"] + ["text"]]

data.to_csv(OUTPUT_FILE, index=False)
