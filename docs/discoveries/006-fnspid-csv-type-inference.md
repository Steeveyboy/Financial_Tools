# 006 — FNSPID must be loaded per file with an all-string `features` schema

- **Verified against:** commit `79b552a` on 2026-09-25, `datasets` 5.0.1
- **Applies to:** `findata/sources/news/extractors/huggingface.py` (`FNSPIDExtractor._iter_rows`)

## What I found

`Zihan1004/FNSPID` is two CSVs loaded by HuggingFace's generic CSV builder,
which lets pandas infer each column's type. The early rows mislead it: the
nasdaq file's `Unnamed: 0` holds `0.0`, and `Publisher` / `Author` are blank,
so they are inferred as `double`. Roughly 1.4M rows in, a text value appears
(`'Интернет и СМИ'`) and the Arrow cast fails:

```
pyarrow.lib.ArrowInvalid: Failed to parse string: 'Интернет и СМИ' as a scalar of type double
datasets.exceptions.DatasetGenerationError: An error occurred while generating the dataset
```

Two further traps:

- **`dtype=str` is not an option in `datasets` 5.x.** `CsvConfig` has no
  `dtype` field; the builder derives the pandas `dtype` from `features`.
- **The two CSVs have different headers.** `Stock_news/nasdaq_exteral_data.csv`
  has a leading `Unnamed: 0` column; `Stock_news/All_external.csv` does not. A
  single `features` schema cannot match both, so each file is loaded on its own
  via `data_files=`.

## Why it bites

With `streaming=False`, `load_dataset` converts the entire ~15.7M-row dataset
to Arrow before yielding one row, so the crash lands minutes in and nothing is
inserted. Streaming alone isn't enough: pandas still infers per chunk, and an
all-blank `Url` chunk would yield float `NaN`, which is truthy and slips past
`_normalise()`'s `if not url` check.

## What to do

Keep `_DATA_FILES` (path → column list) in sync with the dataset, and load each
file with `streaming=True` and
`features=Features({col: Value("string") for col in columns})`. Blank cells
arrive as `None`. `HF_HUB_OFFLINE=1` does not work with `data_files=` on a Hub
repo; the Hub must be reachable (cached files are still reused).
