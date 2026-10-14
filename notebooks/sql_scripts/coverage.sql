select
	a_s.symbol,
	extract(year from a.published_at)::int as year,
	count(distinct a.id) as article_count
from resonance_desk.news.article_securities a_s
join resonance_desk.news.articles a
	on
		a.id = a_s.article_id
group by a_s.symbol, year
order by a_s.symbol, year;
