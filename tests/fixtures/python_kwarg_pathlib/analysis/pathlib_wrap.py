import os
import matplotlib.pyplot as plt
from pathlib import Path

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.path.join(os.getcwd(), 'analysis')

filename = os.path.join(_script_dir, "plots", "chart.png")
path = Path(filename)
path.parent.mkdir(parents=True, exist_ok=True)
plt.savefig(path, dpi=300)
