import os
import pandas as pd

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.path.join(os.getcwd(), 'analysis')

def export(df, output=None):
    if output:
        df.to_csv(output)

export(pd.DataFrame(), output=os.path.join(_script_dir, "..", "output", "final.csv"))
