import pandas as pd
from config import DATA_DIR, OUTPUT_DIR

df = pd.read_parquet(f"{DATA_DIR}/features.parquet")
df.to_parquet(f"{OUTPUT_DIR}/predictions.parquet", index=False)
