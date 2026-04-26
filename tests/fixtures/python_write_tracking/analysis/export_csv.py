import os
import pandas as pd

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.path.join(os.getcwd(), 'analysis')

out_path = os.path.join(_script_dir, "..", "output", "summary.csv")
df = pd.DataFrame()
df.to_csv(out_path, index=False)
