import pandas as pd
import json

def keyQuarters(ls):
    newls = []
    for frame in ls:
        if('frame' in frame.keys()):
            newls.append(frame)
    return newls

def make_frame(df):
    dataModel = json.loads(open('dataModelV3_Income.json', 'r').read())
    incomeModel = dataModel["IncomeStatements"]
    df_model = pd.DataFrame()
    for i in incomeModel:
        try:
            df_model[i] = consolidate(keyQuarters(df[incomeModel[i]]["units"]["USD"]))
        except:
            df_model[i] = None
        # return pd.DataFrame(keyQuarters(df[dataModel[i]]["units"]["USD"]))
        # print(df[dataModel[i]]["units"]["USD"][-1])
        # return pd.DataFrame(df[dataModel[i]]["units"]["USD"])
    return df_model

def consolidate(ls):
    frame = pd.DataFrame(ls)
    frame.fy = frame.end.apply(lambda x: x.split("-")[0])
    # frame.fy = frame.end.apply(lambda x: x.split("-")[0])
    frame = frame[["fy", "val", "frame", "form"]]
    frame = pd.concat([frame, make_q4(frame)])
    # frame["date"] = frame["start"] + ', ' + frame["end"]
    
    frame["frame2"] = frame["frame"].transform(lambda x: x[2:])
    # frame = frame.set_index('frame')
    # frame.drop(["start", "end", "accn", "filed"], axis=1, inplace=True)
    return frame[frame["form"] != "10-K"].sort_values(["fy", "form"]).set_index("frame")["val"]

def make_q4(arr):
    crs = pd.crosstab(arr["fy"], arr["form"], values=arr["val"], aggfunc="sum")
    q = crs["10-K"] - crs["10-Q"]
    out = pd.DataFrame(q.dropna(), columns=["val"]).reset_index()
    out["frame"] = out["fy"].transform(lambda x: f"CY{x}Q4")
    out["form"] = "10-Q"
    return out