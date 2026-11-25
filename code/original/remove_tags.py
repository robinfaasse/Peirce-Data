"""Remove the remaining markup tags from the transcriptions.

Input:  Data/manuscripts_no_del/  (output of remove_deleted_text.py)
Output: Data/manuscripts_clean/   same folders and file names, plain text.

What happens per tag (see README "Markup"):
  - [pn]...[/pn] and [fig]...[/fig] are removed WITH their content:
    page numbers and Gemini's figure descriptions are not Peirce's text.
  - [illegible], [gap], [space] are removed.
  - All other tags ([u], [ins], [i], [marginalia], [date], [math], ...) are
    removed but the words inside them are kept.
  - Markup drift: HTML tags like <u>...</u> and ``` code fences are removed too.
"""
import os
import re

FOLDER = "/Users/robinfaasse/Documents/School/RUG - 2026:2027/Sem 1 - Block 1 + 2/Minor Data Wise/Collaborative Data Project/Data/peirce_transcriptions"
INPUT_DIR = os.path.join(FOLDER, "manuscripts_no_del")
OUTPUT_DIR = os.path.join(FOLDER, "manuscripts_clean")

# Tags whose content is removed as well. Add "date" here if you do not want
# the model to see dates Peirce wrote himself.
DROP_WITH_CONTENT = ["pn", "fig"]

DROP_BLOCK = re.compile(
    r"[\[<](" + "|".join(DROP_WITH_CONTENT) + r")[\]>].*?[\[<]/\1[\]>]",
    re.IGNORECASE | re.DOTALL,
)
ANY_TAG = re.compile(r"\[/?[A-Za-z]+\]|</?[A-Za-z]+>")   # [u], [/u], <u>, </u>, [gap] ...
CODE_FENCE = re.compile(r"^```[a-z]*\s*$", re.MULTILINE)


def clean(text):
    text = DROP_BLOCK.sub(" ", text)
    text = CODE_FENCE.sub("", text)
    text = ANY_TAG.sub("", text)
    text = re.sub(r"[ \t]{2,}", " ", text)          # double spaces
    text = re.sub(r" +([.,;:!?])", r"\1", text)     # space before punctuation
    text = re.sub(r"[ \t]+\n", "\n", text)          # trailing spaces
    text = re.sub(r"\n{3,}", "\n\n", text)          # many blank lines
    return text.strip() + "\n" if text.strip() else ""


files_done = 0
left_over = {}
for root, _, files in os.walk(INPUT_DIR):
    for name in files:
        if not name.endswith(".txt"):
            continue
        in_path = os.path.join(root, name)
        out_path = os.path.join(OUTPUT_DIR, os.path.relpath(in_path, INPUT_DIR))
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(in_path, encoding="utf-8") as f:
            cleaned = clean(f.read())
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(cleaned)
        files_done += 1
        # Report any bracket that still looks like a tag (e.g. [ured2], [Fig.]).
        for t in re.findall(r"\[/?[^\]\s]{1,15}\]", cleaned):
            left_over[t] = left_over.get(t, 0) + 1

print(f"{files_done} files cleaned into {OUTPUT_DIR}")
if left_over:
    print("Brackets still in the text (check if these are tags):")
    for t, n in sorted(left_over.items(), key=lambda x: -x[1])[:20]:
        print(f"  {t}: {n}x")
