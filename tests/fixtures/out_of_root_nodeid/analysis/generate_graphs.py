import os
import pandas as pd

_script_dir = os.path.dirname(os.path.abspath(__file__))
# __file__ is analysis/generate_graphs.py, so ../.. goes up to out_of_root_nodeid parent
data_path = os.path.join(_script_dir, '..', '..', 'results_store')
df = pd.read_parquet(os.path.join(data_path, 'all_results.parquet'))
print(df)
