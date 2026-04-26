import os
import pandas as pd

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.getcwd()

df = pd.DataFrame()
df.to_excel(os.path.join(_script_dir, "output", "report.xlsx"), index=False)
