from flask import Flask, render_template, request
from sentiment.model_wraper import preprocess
from webscrapers import webscraperControl
import pandas as pd
from functools import reduce

app = Flask(__name__)

@app.route("/")
def landing():
    return render_template("index.html", results=[])

@app.route("/searchKeyword", methods=["POST"])
def search_keyword():
    # keyword="hello"

    if request.method == "POST":
        keyword = request.form["keyword"]
        print(f"searching for keyword {keyword}")
    article_list = webscraperControl.main(keyword)

    # lst = pd.read_csv("webscrapers/reuters_tesla.csv").to_dict(orient="records")
    keyword_sentiment = (sum([i["sentiment_score"] for i in article_list]) / len(article_list)) * 100
    # color = get_color(keyword_sentiment)
    # print(article_list)
    return render_template("index.html", results=article_list, keyword_sentiment=keyword_sentiment)
    # return render_template("index.html", results=article_list)

# def get_color(score):
#     if()


if __name__ == "__main__":
    app.run(host="localhost", port=5151, debug=True)