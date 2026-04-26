import os
import pandas as pd

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.path.join(os.getcwd(), 'analysis')

prefix = os.path.join(_script_dir, "..", "output")
suffix = "/results_final.csv"
full_path = prefix + suffix
df = pd.read_csv(full_path)
