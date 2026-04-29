import os
import pickle
import json

RESULTS_BASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "results"
)

cases = ["demand_benchmark", "capacity_low"]
dfs = ["df0", "df1"]

for case in cases:
    for df in dfs:
        path = os.path.join(RESULTS_BASE, case, df)

        # Pattern 1: one-line pickle.load(open(...))
        first_data = pickle.load(open(os.path.join(path, "result_0.pkl"), "rb"))

        # Pattern 2: two-line with context manager
        files = [os.path.join(path, f) for f in os.listdir(path) if f.endswith(".pkl")]
        with open(files[0], "rb") as f:
            data = pickle.load(f)

        # Pattern 3: json.load (should already work for text reads)
        param_path = os.path.join(path, "parameters.json")
        with open(param_path, "r") as f:
            parameters = json.load(f)

print("done")
