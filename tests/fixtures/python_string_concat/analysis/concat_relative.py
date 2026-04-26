import os
import pandas as pd

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.path.join(os.getcwd(), 'analysis')

base = os.path.join(_script_dir, "..", "data") + "/"
df = pd.read_csv(base + "input.csv")
