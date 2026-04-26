import os
import pandas as pd

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.path.join(os.getcwd(), 'analysis')

data_path = os.path.join(_script_dir, '..', 'results') + os.sep
df = pd.read_parquet(f"{data_path}all_results.parquet")
df2 = pd.read_parquet(f"{data_path}all_results_multiT.parquet")
