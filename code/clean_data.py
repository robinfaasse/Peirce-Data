"""Run the whole data cleaning pipeline in one go.

Steps, in this order (each step reads the output of the step before):

  1. remove_deleted_text  manuscripts/          -> manuscripts_no_del/
                          drop text Peirce struck through ([del]...[/del])
  2. remove_tags          manuscripts_no_del/   -> manuscripts_clean/
                          drop [pn] and [fig] with content, all other tags
                          without their content
  3. combine_pages        manuscripts_clean/    -> manuscripts_combined/<ms>.txt
                          + manuscripts_combined_overview.csv
                          one text per manuscript (iiif or microfilm)
  4. correct_date         index.csv + collection_metadata.json
                          -> index_correct_dates.csv
                          every date estimate per source (Irvine, Houghton, Robin)
  5. link_text_and_dates  index_correct_dates.csv + manuscripts_combined/
                          -> manuscripts_dataset.csv
                          one row per manuscript: metadata, dates, n_words, text

The final CSV is written so that it opens cleanly in Apple Numbers / Excel:
utf-8 with BOM (utf-8-sig) and the text of a manuscript on one line, in one
cell (all whitespace collapsed to single spaces).

The original files in manuscripts/ are never changed.

Usage: python code/clean_data.py [folder]   (default: the repo's data/ folder)
"""
import json
import os
import re
import sys

import pandas as pd

# Folder that contains manuscripts/, index.csv and collection_metadata.json.
# By default the data/ folder of this repository, so it works after git clone.
FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")

# Tags whose content is removed as well (step 2). Add "date" here if you do
# not want the model to see dates Peirce wrote himself.
DROP_WITH_CONTENT = ["pn", "fig"]

PAGE_SEPARATOR = "\n\n"

# Date sources in collection_metadata.json and their column prefix (step 4).
SOURCES = {"Irvine": "irvine", "Houghton catalogue": "houghton",
           "Robin catalogue (HTML)": "robin"}
BIRTH, DEATH = 1839, 1914
DATE_COLUMNS = ("dates", "start", "end", "mid", "is_range", "n")


# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------

def transform_txt_files(input_dir, output_dir, func):
    """Apply func to every .txt file under input_dir, keep the folder layout.

    Returns a list of (input path, new text) pairs.
    """
    results = []
    for root, _, files in os.walk(input_dir):
        for name in files:
            if not name.endswith(".txt"):
                continue
            in_path = os.path.join(root, name)
            out_path = os.path.join(output_dir, os.path.relpath(in_path, input_dir))
            os.makedirs(os.path.dirname(out_path), exist_ok=True)
            with open(in_path, encoding="utf-8") as f:
                new_text = func(f.read())
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(new_text)
            results.append((in_path, new_text))
    return results


# --------------------------------------------------------------------------
# Step 1: remove deleted text
# --------------------------------------------------------------------------

# [del]...[/del], also the HTML spelling <del>...</del>; non-greedy, may span lines.
DEL_PATTERN = re.compile(r"\[del\].*?\[/del\]|<del>.*?</del>", re.IGNORECASE | re.DOTALL)


def remove_deleted(text):
    # Repeat so nested deletions ([del]a [del]b[/del] c[/del]) are removed too.
    while True:
        new_text = DEL_PATTERN.sub("", text)
        if new_text == text:
            break
        text = new_text
    # Tidy the gaps left behind: double spaces and a space before punctuation.
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r" +([.,;:!?])", r"\1", text)
    return text


def step_remove_deleted_text(folder):
    results = transform_txt_files(os.path.join(folder, "manuscripts"),
                                  os.path.join(folder, "manuscripts_no_del"),
                                  remove_deleted)
    unclosed = [p for p, text in results if "[del]" in text.lower()]
    if unclosed:
        print(f"Warning: {len(unclosed)} files have a [del] without [/del], e.g. {unclosed[0]}")


# --------------------------------------------------------------------------
# Step 2: remove the remaining tags
# --------------------------------------------------------------------------

DROP_BLOCK = re.compile(
    r"[\[<](" + "|".join(DROP_WITH_CONTENT) + r")[\]>].*?[\[<]/\1[\]>]",
    re.IGNORECASE | re.DOTALL,
)
ANY_TAG = re.compile(r"\[/?[A-Za-z]+\]|</?[A-Za-z]+>")   # [u], [/u], <u>, </u>, [gap] ...
CODE_FENCE = re.compile(r"^```[a-z]*\s*$", re.MULTILINE)


def remove_tags(text):
    text = DROP_BLOCK.sub(" ", text)
    text = CODE_FENCE.sub("", text)
    text = ANY_TAG.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)          # double spaces
    text = re.sub(r" +([.,;:!?])", r"\1", text)     # space before punctuation
    text = re.sub(r"[ \t]+\n", "\n", text)          # trailing spaces
    text = re.sub(r"\n{3,}", "\n\n", text)          # many blank lines
    return text.strip() + "\n" if text.strip() else ""


def step_remove_tags(folder):
    transform_txt_files(os.path.join(folder, "manuscripts_no_del"),
                        os.path.join(folder, "manuscripts_clean"),
                        remove_tags)


# --------------------------------------------------------------------------
# Step 3: combine the pages of each manuscript
# --------------------------------------------------------------------------

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


def step_combine_pages(folder):
    """iiif and microfilm cover the SAME pages, so only one is used: the one
    with the most non-empty pages; iiif (the colour scans) when they are equal.
    """
    input_dir = os.path.join(folder, "manuscripts_clean")
    output_dir = os.path.join(folder, "manuscripts_combined")
    os.makedirs(output_dir, exist_ok=True)

    overview = []
    for manuscript in sorted(os.listdir(input_dir)):
        ms_dir = os.path.join(input_dir, manuscript)
        if not os.path.isdir(ms_dir):
            continue
        iiif = read_pages(os.path.join(ms_dir, "iiif"))
        microfilm = read_pages(os.path.join(ms_dir, "microfilm"))

        if len(iiif) >= len(microfilm) and iiif:
            source, pages = "iiif", iiif
        else:
            source, pages = "microfilm", microfilm

        text = PAGE_SEPARATOR.join(pages)
        with open(os.path.join(output_dir, manuscript + ".txt"), "w", encoding="utf-8") as f:
            f.write(text)

        overview.append({
            "folder": manuscript,
            "houghton_id": manuscript.split("_", 1)[-1],
            "source_used": source if pages else "none",
            "iiif_pages_with_text": len(iiif),
            "microfilm_pages_with_text": len(microfilm),
            "n_words": len(text.split()),
        })

    pd.DataFrame(overview).to_csv(
        os.path.join(folder, "manuscripts_combined_overview.csv"), index=False)


# --------------------------------------------------------------------------
# Step 4: every date estimate per source
# --------------------------------------------------------------------------

def years_of(value):
    """All four-digit years in a date value ('1898/1899', '1896-12-05', ...)."""
    return [int(y) for y in re.findall(r"(?<!\d)(\d{4})(?!\d)", value or "")]


def collect_dates(folder):
    """houghton_id -> list of (prefix, value, precision)."""
    with open(os.path.join(folder, "collection_metadata.json"), encoding="utf-8") as f:
        metadata = json.load(f)
    entries = {}
    for rec in metadata:
        for e in rec["dating"]:
            if e["value"]:
                entries.setdefault(rec["id"], []).append(
                    (SOURCES[e["source"]], e["value"], e["precision"]))
    return entries


def step_correct_date(folder):
    """No source is preferred. Per source: <prefix>_dates, _start, _end, _mid,
    _is_range, _n. Full dates are reduced to their year; a date with a year
    before 1839 or after 1914 is dropped.
    """
    index = pd.read_csv(os.path.join(folder, "index.csv"), dtype=str, keep_default_na=False)
    entries = collect_dates(folder)

    rows = []
    for hid in index["houghton_id"]:
        per_source = {}
        for prefix, value, precision in entries.get(hid, []):
            years = years_of(value)
            if not years or max(years) > DEATH or min(years) < BIRTH:
                continue
            per_source.setdefault(prefix, []).append((value, years, precision))

        row = {}
        for prefix in SOURCES.values():
            found = per_source.get(prefix, [])
            if not found:
                row.update({f"{prefix}_{c}": None for c in DATE_COLUMNS})
                continue
            all_years = [y for _, ys, _ in found for y in ys]
            start, end = min(all_years), max(all_years)
            row[f"{prefix}_dates"] = "; ".join(v for v, _, _ in found)
            row[f"{prefix}_start"] = start
            row[f"{prefix}_end"] = end
            row[f"{prefix}_mid"] = (start + end) / 2
            row[f"{prefix}_is_range"] = any(p == "range" or len(set(ys)) > 1
                                            for _, ys, p in found)
            row[f"{prefix}_n"] = len(found)
        rows.append(row)

    dates = pd.DataFrame(rows, columns=[f"{p}_{c}" for p in SOURCES.values()
                                        for c in DATE_COLUMNS])
    for prefix in SOURCES.values():
        for c in ("start", "end", "n"):
            dates[f"{prefix}_{c}"] = dates[f"{prefix}_{c}"].astype("Int64")
        dates[f"{prefix}_is_range"] = dates[f"{prefix}_is_range"].astype("boolean")

    out = pd.concat([index.drop(columns=["catalogue_dates"]), dates], axis=1)
    out.to_csv(os.path.join(folder, "index_correct_dates.csv"), index=False)


# --------------------------------------------------------------------------
# Step 5: link text and dates
# --------------------------------------------------------------------------

def step_link_text_and_dates(folder):
    """Link key: the folder name. package_path is
    "manuscripts/MS-0001_hou02614c00003" and step 3 saved that manuscript as
    "MS-0001_hou02614c00003.txt". Only manuscripts with text are kept.
    """
    sources = list(SOURCES.values())
    text_dir = os.path.join(folder, "manuscripts_combined")

    # Metadata and dates: one row per catalogue record.
    index = pd.read_csv(
        os.path.join(folder, "index_correct_dates.csv"),
        dtype={"robin": str, "houghton_id": str,
               **{f"{s}_dates": str for s in sources},
               **{f"{s}_{c}": "Int64" for s in sources for c in ("start", "end", "n")}})
    index["package_path"] = index["package_path"].fillna("")
    index["folder"] = index["package_path"].apply(lambda p: os.path.basename(p) if p else "")

    # Texts: one row per combined .txt file, whitespace collapsed to one line.
    texts = []
    for name in os.listdir(text_dir):
        if name.endswith(".txt"):
            with open(os.path.join(text_dir, name), encoding="utf-8") as f:
                texts.append({"folder": name[:-4], "text": " ".join(f.read().split())})
    texts = pd.DataFrame(texts, columns=["folder", "text"])

    # Link: keep manuscripts that have both a row in the index and text.
    data = index[index["folder"] != ""].merge(texts, on="folder", how="inner",
                                              validate="one_to_one")
    data = data[data["text"] != ""]

    # Extra columns; the text goes last.
    data["has_date"] = data[[f"{s}_start" for s in sources]].notna().any(axis=1)
    data["n_words"] = data["text"].str.split().str.len()
    data = data[[c for c in data.columns if c != "text"] + ["text"]]

    data.to_csv(os.path.join(folder, "manuscripts_dataset.csv"), index=False,
                encoding="utf-8-sig")


# --------------------------------------------------------------------------

def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else FOLDER
    step_remove_deleted_text(folder)
    step_remove_tags(folder)
    step_combine_pages(folder)
    step_correct_date(folder)
    step_link_text_and_dates(folder)
    print(f"Done: {os.path.normpath(os.path.join(folder, 'manuscripts_dataset.csv'))}")


if __name__ == "__main__":
    main()
