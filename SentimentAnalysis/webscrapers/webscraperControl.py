# import sys
# sys.path.insert(0, "..")

from sentiment import model_wraper
sentiment_model = model_wraper.load_model()
import pandas as pd
from . import reuters, CBC




def agg_articles(keyword):
    cbc_articles = CBC.main(keyword)
    reuters_articles = reuters.main(keyword)
    return pd.concat([cbc_articles, reuters_articles])

def main(keyword):
    data = agg_articles(keyword)
    data["sentiment_score"] = model_wraper.analyse_articles(sentiment_model, data)
    return data.sample(fraq=1).to_dict(orient="records")
