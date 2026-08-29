from requests_html import AsyncHTMLSession, HTMLSession
import pandas as pd
import requests, asyncio
# from sentiment import model_wraper
# sentiment_model = model_wraper.load_model()

source = "https://www.reuters.com"

link = "https://www.reuters.com/pf/api/v3/content/fetch/articles-by-search-v2?query=%7B%22keyword%22%3A%22{keyword}%22%2C%22offset%22%3A0%2C%22orderby%22%3A%22display_date%3Adesc%22%2C%22size%22%3A{count}%2C%22website%22%3A%22reuters%22%7D&&_website=reuters"

# link = "https://www.reuters.com/pf/api/v3/content/fetch/articles-by-search-v2?query=%7B%22keyword%22%3A%22{keyword}%22%2C%22offset%22%3A0%2C%22orderby%22%3A%22display_date%3Adesc%22%2C%22size%22%3A{count}%2C%22website%22%3A%22reuters%22%7D&d=114&_website=reuters"

#https://www.reuters.com/pf/api/v3/content/fetch/articles-by-search-v2?query=%7B%22keyword%22%3A%22tesla%22%2C%22offset%22%3A0%2C%22orderby%22%3A%22display_date%3Adesc%22%2C%22size%22%3A20%2C%22website%22%3A%22reuters%22%7D&d=108&_website=reuters

#Link notes
#   Figure out what d=xxx means. SOLVED? you can omit this and link still works


def fetch_data(keyword):
    res = requests.get(link.format(keyword=keyword, count=20))
    if(res.ok):
        return parse_data(res)
    else:
        # print(res)
        return None

def create_article_element(data):
    # dc = {"Source": "https://www.reuters.com/"}
    articles = []
    for i in data:
        try:
            articles.append({"Source": "https://www.reuters.com/", "title": i["title"], "description": i["description"], "url": ("https://www.reuters.com" + i["canonical_url"]), "image":i["thumbnail"]["renditions"]["original"]["480w"], "date": i["published_time"]})
        except:
            pass
    return articles

def parse_data(res):
    data = res.json()["result"]["articles"]
    ls = create_article_element(data)
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
    # data["sentiment_score"] = model_wraper.analyse_articles(sentiment_model, data)
    if getarticles:
        urls = list(data["url"])
        articles = asyncio.run(get_articles(urls))
        data["article"] = articles
    # data.to_csv(f"reuters_{keyword}.csv", index=False)
    # return data.to_dict(orient="records")
    return data

    

# if __name__ == "__main__":
#     results = main("tesla", getarticles=True)
