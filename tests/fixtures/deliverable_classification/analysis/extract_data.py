import pandas as pd

# Writes an intermediate parquet — consumed by generate_graphs.py
df = pd.DataFrame({'value': [1, 2, 3]})
df.to_parquet("results/all_results.parquet", index=False)

# Also writes a CSV consumed by generate_graphs.py
df.to_csv("results/summary.csv", index=False)

# Also writes an xlsx consumed by generate_graphs.py
df.to_excel("results/summary.xlsx", index=False)
