import os
import sys
import pandas as pd

# f-string with only runtime variable in filename
env_var = os.environ.get("FILENAME")
path = f"./data/{env_var}.parquet"
df = pd.read_parquet(path)

# os.path.join with only directory prefix resolved
prefix = "../output"
name = sys.argv[1]
path2 = os.path.join(prefix, name + ".pdf")
with open(path2) as f:
    pass

# Empty string concatenation (should resolve cleanly)
base = ""
path3 = base + "data.csv"
df2 = pd.read_csv(path3)
