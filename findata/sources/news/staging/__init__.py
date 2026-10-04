"""
findata.sources.news.staging

Raw loaders: copy a dataset as-is into a staging table. No deduplication, no
normalization — that is the job of a later transform into ``news.articles``.
"""
