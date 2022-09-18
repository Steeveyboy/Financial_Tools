from flask import Flask, render_template
from webscrapers import reuters

app = Flask(__name__)

@app.route("/")
def landing():
    return render_template("index.html", results=[])

@app.route("/searchKeyword/<keyword>", methods=["GET"])
def search_keyword(keyword):
    article_list = reuters.main(keyword)
    # print(article_list)
    return render_template("index.html", results=article_list)

if __name__ == "__main__":
    app.run(host="localhost", port=5151, debug=True)