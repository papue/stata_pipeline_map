import pandas as pd
a = "../data"
b = "/sub"
c = "/file.csv"
path = a + b + c
df = pd.read_csv(path)
