import os
import matplotlib.pyplot as plt

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.path.join(os.getcwd(), 'analysis')

output_dir = os.path.join(_script_dir, "plots")
fig, ax = plt.subplots()
fig.savefig(os.path.join(output_dir, "output_chart.png"), bbox_inches="tight")
