### Table of contents
### 1. Import data
### 2. Boxplots
###     2.1 Define Function
###     2.2 Generate Figures
### 3. Boxplots - comparing cases

# test

### 1. Import data

import pandas as pd
df = pd.read_csv("results/output.csv")

### 2. Boxplots - by case

import matplotlib.pyplot as plt

### 2.1 Define Function

def make_boxplot(df):
    fig, ax = plt.subplots()
    return fig, ax

### 2.2 Generate Figures

fig, ax = make_boxplot(df)
plt.savefig("output/boxplot.png")

### 3. Boxplots - comparing cases

fig2, ax2 = make_boxplot(df)
plt.savefig("output/compare.png")
