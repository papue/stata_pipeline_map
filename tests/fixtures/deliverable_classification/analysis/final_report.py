import pandas as pd

# Writes a CSV that nobody reads — this one should be deliverable
df = pd.DataFrame({'result': [42]})
df.to_csv("output/final_table.csv", index=False)
