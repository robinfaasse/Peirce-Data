"""Build index_correct_dates.csv: index.csv plus every date estimate per source.

No source is preferred over another. For each source there is a set of columns
(prefix = irvine, houghton, robin):

  <prefix>_dates     every date the source gives, as written in the metadata,
                     separated by "; " (e.g. "1898/1899" or "1904; 1908")
  <prefix>_start     earliest year over those dates
  <prefix>_end       latest year over those dates
  <prefix>_mid       (start + end) / 2, a single year if one is needed
  <prefix>_is_range  True if at least one of the dates is a range (e.g. 1898-99)
  <prefix>_n         number of dates the source gives

Full dates (1896-12, February 5, 1912) are reduced to their year.
A date (or range) containing a year after 1914 (Peirce's death) or before 1839
(his birth) is dropped: it cannot be a date of composition.

Sources: Irvine, Houghton catalogue and Robin catalogue (HTML), all taken from
collection_metadata.json. Kloesel and Pietarinen (only 10 dates, in dates.csv)
are left out.

Usage: python correct_date.py [folder]   (default: FOLDER below)
"""
import json
import os
import re
import sys

import pandas as pd

FOLDER = "/Users/robinfaasse/Documents/School/RUG - 2026:2027/Sem 1 - Block 1 + 2/Minor Data Wise/Collaborative Data Project/Data/peirce_transcriptions"
SOURCES = {"Irvine": "irvine", "Houghton catalogue": "houghton",
           "Robin catalogue (HTML)": "robin"}
BIRTH, DEATH = 1839, 1914
COLUMNS = ("dates", "start", "end", "mid", "is_range", "n")


def years_of(value):
    """All four-digit years in a date value ('1898/1899', '1896-12-05', ...)."""
    return [int(y) for y in re.findall(r"(?<!\d)(\d{4})(?!\d)", value or "")]


def collect(folder):
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


def main():
    folder = sys.argv[1] if len(sys.argv) > 1 else FOLDER
    index = pd.read_csv(os.path.join(folder, "index.csv"), dtype=str, keep_default_na=False)
    entries = collect(folder)

    rows = []
    for hid in index["houghton_id"]:
        per_source = {}
        for prefix, value, precision in entries.get(hid, []):
            years = years_of(value)
            if not years:
                continue
            if max(years) > DEATH or min(years) < BIRTH:
                continue
            per_source.setdefault(prefix, []).append((value, years, precision))

        row = {}
        for prefix in SOURCES.values():
            found = per_source.get(prefix, [])
            if not found:
                row.update({f"{prefix}_{c}": None for c in COLUMNS})
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

    dates = pd.DataFrame(rows)
    for prefix in SOURCES.values():
        for c in ("start", "end", "n"):
            dates[f"{prefix}_{c}"] = dates[f"{prefix}_{c}"].astype("Int64")
        dates[f"{prefix}_is_range"] = dates[f"{prefix}_is_range"].astype("boolean")

    out = pd.concat([index.drop(columns=["catalogue_dates"]), dates], axis=1)
    out.to_csv(os.path.join(folder, "index_correct_dates.csv"), index=False)


if __name__ == "__main__":
    main()
