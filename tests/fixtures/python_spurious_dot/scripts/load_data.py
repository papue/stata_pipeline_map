import pandas as pd

DATASET = "train"  # literal — should be fully resolvable
df = pd.read_csv("../data/" + DATASET + ".csv")
