# Table of contents:
## 0. Helper functions
## 1. Load data
## 2. Process data

import pandas as pd

## 1. Load data
df = pd.read_csv("data/input.csv")

## 2. Process data
df = df.dropna()
df.to_csv("data/processed.csv")
