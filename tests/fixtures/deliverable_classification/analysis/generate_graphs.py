import pandas as pd
import matplotlib.pyplot as plt

# Reads the intermediate files
df1 = pd.read_parquet("results/all_results.parquet")
df2 = pd.read_csv("results/summary.csv")
df3 = pd.read_excel("results/summary.xlsx")

fig, ax = plt.subplots()
ax.plot(df1['value'])
plt.savefig("output/plot.png", dpi=300)
