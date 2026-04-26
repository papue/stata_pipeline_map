import sys
import pandas as pd

DATASET = sys.argv[1]  # runtime
df = pd.read_csv("../data/" + DATASET + ".csv")
