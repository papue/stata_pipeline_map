import pandas as pd

## 1. Setup
df = pd.read_csv("data/phase1_input.csv")

# lots of phase 1 code...
x = df.groupby("id").mean()

## 1. Setup
df2 = pd.read_csv("data/phase2_input.csv")

# lots of phase 2 code...
y = df2.groupby("id").mean()
