# %% 1. Load data
import pandas as pd
df = pd.read_csv("data/clean.csv")

## 2. Run regressions
# ---- 2.1 OLS ----
from sklearn.linear_model import LinearRegression
# x = 5  # this is NOT a section

### 2.2 Fixed effects
