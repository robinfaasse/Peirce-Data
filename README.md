# Peirce data

Data cleaning for the Peirce manuscripts (Collaborative Data Project).

## Run

Set `FOLDER` at the top of `code/clean_data.py` to the `peirce_transcriptions`
folder (the one with `manuscripts/`, `index.csv` and `collection_metadata.json`), then:

```
python code/clean_data.py
```

or pass the folder: `python code/clean_data.py /path/to/peirce_transcriptions`.

It runs all steps in order and writes `manuscripts_dataset.csv`:

1. remove deleted text (`manuscripts_no_del/`)
2. remove tags (`manuscripts_clean/`)
3. combine pages (`manuscripts_combined/`, `manuscripts_combined_overview.csv`)
4. date estimates per source (`index_correct_dates.csv`)
5. link text and dates (`manuscripts_dataset.csv`, utf-8-sig, text in one cell)

`code/original/` holds the five separate scripts the pipeline was built from.
