import os
import pandas as pd

path_base = r"C:\project_external\results"
save_path = os.path.join(path_base, "all_results.parquet")
df = pd.DataFrame({"x": [1, 2, 3]})
df.to_parquet(save_path, index=False)
