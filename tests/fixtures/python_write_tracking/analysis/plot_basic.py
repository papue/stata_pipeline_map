import os
import matplotlib.pyplot as plt

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.path.join(os.getcwd(), 'analysis')

plot_name = "Market prices and avg quantity bids"
plt.savefig(os.path.join(_script_dir, "plots", f"{plot_name}.png"), dpi=300)
