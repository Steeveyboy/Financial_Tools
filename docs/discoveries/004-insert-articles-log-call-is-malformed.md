# 004 — `insert_articles()`'s success log line has more args than format specs

- **Verified against:** commit `b675cfb` on 2026-08-21
- **Applies to:** `findata/sources/news/db/repository.py`

## What I found

The summary log at the end of `ArticleRepository.insert_articles()` passes three
arguments to a format string with one specifier:

```python
_logger.info(
    "Inserted %d articles",
    len(to_insert),
    f" (skipped {skipped} duplicates)" if skipped else "",
    f" (%.3f seconds)" % (end_time - start_time),
)
```

`logging` catches the resulting `TypeError` internally and prints a
"--- Logging error ---" traceback to stderr instead of the message. The insert
itself succeeds — only the reporting is lost.

The intended line is presumably
`"Inserted %d articles%s%s"` with the three arguments.

## Why it bites

The main progress signal of the extraction pipeline is replaced by a traceback,
which reads like the pipeline crashed when it didn't. Don't chase it as an
insert failure.

## What to do

Fix the format string when next touching this file. Note `repository.py` had
uncommitted local edits at the time of writing, so check the working tree before
assuming it's still broken.
