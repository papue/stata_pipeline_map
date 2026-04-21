import pandas as pd
df = pd.read_csv("data/input.csv")
df.to_stata("data/output.dta")
