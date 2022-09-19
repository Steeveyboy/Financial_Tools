from flask import Flask, render_template, request
from webscrapers import reuters
import pandas as pd


app = Flask(__name__)

@app.route("/")
def landing():
    return render_template("index.html", results=[])

@app.route("/searchKeyword", methods=["POST"])
def search_keyword():
    keyword="hello"

    if request.method == "POST":
        keyword = request.form["keyword"]
    article_list = reuters.main(keyword)
    # lst = pd.read_csv("webscrapers/reuters_tesla.csv").to_dict(orient="records")


    # print(article_list)
    return render_template("index.html", results=article_list)
    # return render_template("index.html", results=article_list)

if __name__ == "__main__":
    app.run(host="localhost", port=5151, debug=True)