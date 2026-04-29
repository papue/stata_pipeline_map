import os
import pickle

RESULTS_BASE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "results", "demand_benchmark"
)

DEMAND_FACTORS = ["df-1", "df0", "df1"]


def load_pkl_files(folder: str) -> list:
    pkl_files = sorted(
        f for f in os.listdir(folder)
        if f.endswith(".pkl") and os.path.isfile(os.path.join(folder, f))
    )
    result = []
    for fname in pkl_files:
        with open(os.path.join(folder, fname), "rb") as fh:
            result.append(pickle.load(fh))
    return result


for df_name in DEMAND_FACTORS:
    folder = os.path.join(RESULTS_BASE, df_name)
    pkl_list = load_pkl_files(folder)

print("done")
