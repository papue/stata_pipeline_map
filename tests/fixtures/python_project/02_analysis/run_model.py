"""Stage 2: Run regression model and export results."""
import pandas as pd
import matplotlib.pyplot as plt
from utils.helpers import normalize_columns

OUTPUT_DIR = "results"

# Read cleaned data
df = pd.read_parquet("data/clean/survey_clean.parquet")

# Run model (placeholder)
results = df.describe()

# Write outputs
results.to_csv("results/summary_stats.csv")
plt.savefig("results/income_distribution.png")
