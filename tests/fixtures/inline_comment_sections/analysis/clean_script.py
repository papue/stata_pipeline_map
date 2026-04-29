### 1. Load data

import pandas as pd
df = pd.read_csv("data/raw.csv")

### 2. Clean

df = df.dropna()
df = df[df['value'] > 0]

### 3. Save

df.to_csv("data/clean.csv", index=False)
