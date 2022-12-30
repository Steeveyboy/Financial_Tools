from requests_html import HTMLSession
import pandas as pd
import requests, asyncio, logging
link = "https://www.cbc.ca/search_api/v1/search?q={keyword}&sortOrder=relevance&section=news&media=all&boost-cbc-keywords=7&boost-cbc-keywordscollections=7&boost-cbc-keywordslocation=4&boost-cbc-keywordsorganization=3&boost-cbc-keywordsperson=5&boost-cbc-keywordssubject=7&boost-cbc-publishedtime=30&page=1&fields=feed"
# link = "https://www.cbc.ca/search_api/v1/search?q=tesla&sortOrder=relevance&media=all&boost-cbc-keywords=7&boost-cbc-keywordscollections=7&boost-cbc-keywordslocation=4&boost-cbc-keywordsorganization=3&boost-cbc-keywordsperson=5&boost-cbc-keywordssubject=7&boost-cbc-publishedtime=30&page=1&fields=feed"

def fetch_article_headlines(keyword):
    res = requests.get(link.format(keyword=keyword))
    if(res.ok):
        return parse_data(res)
    else:
        return None

def parse_data(res):
    data = res.json()
    ls = create_article_element(data)
    df = pd.DataFrame(ls)
    df["date"] = pd.to_datetime(df["date"]).dt.date
    return df

def create_article_element(data):
    # dc = {"Source": "https://www.reuters.com/"}
    articles = []
    for i in data:
        try:
            articles.append({"Source": "https://www.cbc.ca/", "title": i["title"], "description": i["description"], "url": (i["url"]), "image":i["dominantimage"], "date": i["publishtime"]})
        except:
            pass
    return articles


def parse_headlines():
    pass

def fetch_articles():
    pass


def main(keyword, getarticles=False):
    data = fetch_article_headlines(keyword)
    data["keyword"] = keyword
    
    if getarticles:
        pass
        # urls = list(data["url"])
        # articles = asyncio.run(get_articles(urls))
        # data["article"] = articles

    # data.to_csv(f"cbc_{keyword}.csv", index=False)
    return data
    # return data.to_dict(orient="records")

if __name__ == "__main__":
    results = main("tesla", getarticles=True)