### Table of contents
### 0. Helper functions
###     0.1 Check Constant Action
### 1. Collect data
### 2. Save results

# test comment

### 0. Helper functions

def helper():
    pass

### 0.1 Check Constant Action

def check_constant(data):
    return data

###     0.2 Validate data

def validate(df):
    return df

### 1. Collect data

data = [1, 2, 3]

### 2. Save results

import pandas as pd
pd.DataFrame({'x': data}).to_csv("results/output.csv", index=False)
