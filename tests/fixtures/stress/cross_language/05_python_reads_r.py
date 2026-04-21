import pandas as pd
df = pd.read_csv("output/final_results.csv")
df.to_excel("output/summary.xlsx")
