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

    if request.method == "POST":
        keyword = request.form["keyword"]
        print(f"searching for keyword {keyword}")

    if keyword == "":
        return landing()

    article_list = webscraperControl.main(keyword)
    keyword_sentiment = (sum([i["sentiment_score"] for i in article_list]) / len(article_list)) * 100


    return render_template("index.html", results=article_list, keyword_sentiment=keyword_sentiment)
    # return render_template("index.html", results=article_list)

# def get_color(score):
#     if()


if __name__ == "__main__":
    app.run(host="localhost", port=5151, debug=True)