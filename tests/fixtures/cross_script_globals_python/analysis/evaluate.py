import pandas as pd
from config import DATA_DIR, OUTPUT_DIR

df = pd.read_parquet(f"{OUTPUT_DIR}/predictions.parquet")
df.to_csv(f"{OUTPUT_DIR}/evaluation.csv", index=False)
