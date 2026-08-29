import pickle, re, string, pandas
from nltk.corpus import stopwords

stopSet = set(stopwords.words("english"))
puncSet = set(list(string.punctuation) + ["\n", ""])

cleanword = lambda word: ((word not in puncSet) and (word.isalpha()) and (len(word)>1))
# global sentiment_model

def preprocess(words, string=False):
    if(type(words) == str):
        words = re.sub(r"\s+", " ", words)
        words = re.sub(r"[^a-zA-Z\s]", "", words)
        words = words.split(" ")
    
    clean_mess = [w.lower() for w in words if w.lower() not in stopSet and cleanword(w)]
    if(string):
        return " ".join(clean_mess)
    else:
        return clean_mess

def analyse_articles(sentiment_model, df):
    return sentiment_model.predict_proba(df.description).transpose()[1].round(3)

def load_model():
    filer = open("sentiment/sentiment_pipeline.pickle", "rb")
    sentiment_model = pickle.load(filer)
    return sentiment_model

