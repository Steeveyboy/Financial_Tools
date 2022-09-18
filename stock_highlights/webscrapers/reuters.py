from requests_html import AsyncHTMLSession
import pandas as pd
import requests, asyncio

source = "https://www.reuters.com"
link = "https://www.reuters.com/pf/api/v3/content/fetch/articles-by-search-v2?query=%7B%22keyword%22%3A%22{keyword}%22%2C%22offset%22%3A0%2C%22orderby%22%3A%22display_date%3Adesc%22%2C%22size%22%3A{count}%2C%22website%22%3A%22reuters%22%7D&d=108&_website=reuters"

def fetch_data(keyword):
    res = requests.get(link.format(keyword=keyword, count=20))
    if(res.ok):
        return parse_data(res)
    else:
        return None

def parse_data(res):
    data = res.json()["result"]["articles"]
    ls = [{"Source": "https://www.reuters.com/", "title": i["title"], "description": i["description"], "url": ("https://www.reuters.com" + i["canonical_url"]), "image":i["thumbnail"]["renditions"]["original"]["60w"], "date": i["published_time"]} for i in data]
    df = pd.DataFrame(ls)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df

async def fetch_article(session, url):
    res = await session.get(url)
    text = res.html.find("#main-content div.article-body__content__17Yit", first=True).text
    return text

async def get_articles(urls):
    session = AsyncHTMLSession()
    tasks = [fetch_article(session, url) for url in urls]
    articles = await asyncio.gather(*tasks)
    return articles

def main(keyword, getarticles=False):
    data = fetch_data(keyword)
    data["keyword"] = keyword
    
    if getarticles:
        urls = list(data["url"])
        articles = asyncio.run(get_articles(urls))
        data["article"] = articles
    return data.to_dict(orient="records")
    # data.to_csv(f"reuters_{keyword}.csv")

if __name__ == "__main__":
    main("tesla", False)
