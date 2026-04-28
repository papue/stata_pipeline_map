import os
import matplotlib.pyplot as plt

_script_dir = os.path.dirname(os.path.abspath(__file__))
plot_name = "baseline"

fig, ax = plt.subplots()
ax.plot([1, 2, 3])
plt.savefig(os.path.join(_script_dir, "plots", f"{plot_name}.png"), dpi=300, bbox_inches="tight")
