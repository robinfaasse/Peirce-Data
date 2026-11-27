# Peirce data

Data cleaning and dating models for the Peirce manuscripts (Collaborative Data Project).

## Contents

- `data/manuscripts/`: raw transcriptions, one folder per manuscript (`iiif/` and `microfilm/` pages). See `data/README.md` for the layout and the markup.
- `data/index.csv`, `data/collection_metadata.json`: catalogue metadata and dates.
- `code/clean_data.py`: the whole cleaning pipeline in one script.
- `code/original/`: the five separate scripts the pipeline was built from.

## Run

```
git clone https://github.com/robinfaasse/Peirce-Data.git
cd Peirce-Data
pip install pandas
python code/clean_data.py
```

No path to change: the script uses the repo's `data/` folder. To run it on another folder, pass it as argument: `python code/clean_data.py /path/to/folder`.

Steps, in order:

1. remove deleted text (`data/manuscripts_no_del/`)
2. remove tags (`data/manuscripts_clean/`)
3. combine pages (`data/manuscripts_combined/`, `data/manuscripts_combined_overview.csv`)
4. date estimates per source (`data/index_correct_dates.csv`)
5. link text and dates (`data/manuscripts_dataset.csv`, utf-8-sig, text in one cell)

All outputs are generated, so they are in `.gitignore`; run the script to make them.

## Dating models

`code/dating/` holds three models that estimate the year of a manuscript with
an 80% and 95% range, compared with grouped 5-fold cross-validation. See
[`code/dating/README.md`](code/dating/README.md) for the design and results.

```
pip install -r requirements.txt
python code/clean_data.py
python code/dating/train_evaluate.py
python code/dating/predict.py data/manuscripts/MS-0001_hou02614c00003
python code/dating/app.py      # upload page on http://localhost:8000
```
