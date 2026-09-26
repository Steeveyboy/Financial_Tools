with temptable as (
    select
        article_id,
        array_agg(symbol) as symbols,
        count(*) as symbol_count
    from resonance_desk.news.article_securities
    group by article_id
)
select
    a.id,
    a.title,
    a.url,
    a.published_at,
    unnest(t.symbols) as symbol,
    t.symbol_count
from temptable t
join resonance_desk.news.articles a on a.id = t.article_id
where t.symbol_count > 1
and t.symbol_count < 50
order by t.symbol_count desc;