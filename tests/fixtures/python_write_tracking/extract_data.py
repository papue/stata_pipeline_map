import os
import pandas as pd

path_base = r"C:\project\results"
save_path = os.path.join(path_base, "all_results.parquet")
df = pd.DataFrame()
df.to_parquet(save_path, index=False)
