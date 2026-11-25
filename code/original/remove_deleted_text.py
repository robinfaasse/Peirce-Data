"""Remove text Peirce struck through: everything between [del] and [/del].

Input:  Data/manuscripts/<folder>/{iiif,microfilm}/*.txt
Output: Data/manuscripts_no_del/ with the same folders and file names.
        The original files are not changed.
"""
import os
import re

# Folder with the manuscripts folder (here: ../Data next to the Code folder).
FOLDER = "/Users/robinfaasse/Documents/School/RUG - 2026:2027/Sem 1 - Block 1 + 2/Minor Data Wise/Collaborative Data Project/Data/peirce_transcriptions"
INPUT_DIR = os.path.join(FOLDER, "manuscripts")
OUTPUT_DIR = os.path.join(FOLDER, "manuscripts_no_del")

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


files_done = 0
files_changed = 0
unclosed = []

for root, _, files in os.walk(INPUT_DIR):
    for name in files:
        if not name.endswith(".txt"):
            continue
        in_path = os.path.join(root, name)
        out_path = os.path.join(OUTPUT_DIR, os.path.relpath(in_path, INPUT_DIR))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        with open(in_path, encoding="utf-8") as f:
            text = f.read()
        cleaned = remove_deleted(text)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(cleaned)

        files_done += 1
        if cleaned != text:
            files_changed += 1
        if "[del]" in cleaned.lower():
            unclosed.append(in_path)

print(f"{files_done} files processed, {files_changed} had deleted text removed")
if unclosed:
    print(f"{len(unclosed)} files still contain a [del] without a closing [/del], e.g.:")
    for p in unclosed[:5]:
        print("  ", p)
