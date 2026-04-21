import pandas as pd
df = pd.read_stata("intermediate/clean_data.dta")
df.to_csv("intermediate/transformed.csv", index=False)
