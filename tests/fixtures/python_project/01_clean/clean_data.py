"""Stage 1: Load and clean raw survey data."""
import pandas as pd
from utils.helpers import normalize_columns

RAW_DIR = "data/raw"
CLEAN_DIR = "data/clean"

# Read raw data
df = pd.read_csv("data/raw/survey.csv")
df_xl = pd.read_excel("data/raw/survey_extra.xlsx")

# Normalize and combine
df = normalize_columns(df)

# Write cleaned outputs
df.to_parquet("data/clean/survey_clean.parquet")
df.to_csv("data/clean/survey_clean.csv", index=False)
