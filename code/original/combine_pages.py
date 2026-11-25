"""Combine all pages of each manuscript into one .txt file.

Input:  Data/manuscripts_clean/<manuscript>/{iiif,microfilm}/*.txt
Output: Data/manuscripts_combined/<manuscript>.txt   one file per manuscript
        Data/manuscripts_combined_overview.csv       which source was used

A manuscript can have iiif pages, microfilm pages, or both. The two sources
cover the SAME pages, so only one is used: the one with the most non-empty
pages; iiif (the colour scans) when they are equal.
Pages are joined in page order, empty pages are skipped.
"""
import os
import re

import pandas as pd

FOLDER = "/Users/robinfaasse/Documents/School/RUG - 2026:2027/Sem 1 - Block 1 + 2/Minor Data Wise/Collaborative Data Project/Data/peirce_transcriptions"
INPUT_DIR = os.path.join(FOLDER, "manuscripts_clean")
OUTPUT_DIR = os.path.join(FOLDER, "manuscripts_combined")
PAGE_SEPARATOR = "\n\n"


def page_order(filename):
    """Sort key: seq2 before seq10, R-1_0009 before R-1_0010, R-1 before R-2.

    Separately catalogued pages (hou..._seq1.txt) go after the normal pages.
    """
    special = filename.startswith("hou")
    numbers = [int(n) for n in re.findall(r"\d+", filename)]
    return (special, numbers, filename)


def read_pages(source_dir):
    """Return the non-empty page texts of one source folder, in page order."""
    if not os.path.isdir(source_dir):
        return []
    names = sorted((n for n in os.listdir(source_dir) if n.endswith(".txt")), key=page_order)
    pages = []
    for name in names:
        with open(os.path.join(source_dir, name), encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            pages.append(text)
    return pages


os.makedirs(OUTPUT_DIR, exist_ok=True)
overview = []
for manuscript in sorted(os.listdir(INPUT_DIR)):
    ms_dir = os.path.join(INPUT_DIR, manuscript)
    if not os.path.isdir(ms_dir):
        continue
    iiif = read_pages(os.path.join(ms_dir, "iiif"))
    microfilm = read_pages(os.path.join(ms_dir, "microfilm"))

    if len(iiif) >= len(microfilm) and iiif:
        source, pages = "iiif", iiif
    else:
        source, pages = "microfilm", microfilm

    text = PAGE_SEPARATOR.join(pages)
    with open(os.path.join(OUTPUT_DIR, manuscript + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)

    overview.append({
        "folder": manuscript,
        "houghton_id": manuscript.split("_", 1)[-1],
        "source_used": source if pages else "none",
        "iiif_pages_with_text": len(iiif),
        "microfilm_pages_with_text": len(microfilm),
        "n_words": len(text.split()),
    })

df = pd.DataFrame(overview)
df.to_csv(os.path.join(FOLDER, "manuscripts_combined_overview.csv"), index=False)
print(f"{len(df)} manuscripts combined into {OUTPUT_DIR}")
print(df["source_used"].value_counts().to_string())
empty = df[df["n_words"] == 0]
if len(empty):
    print(f"{len(empty)} manuscripts have no text left, e.g. {', '.join(empty['folder'].head(5))}")
