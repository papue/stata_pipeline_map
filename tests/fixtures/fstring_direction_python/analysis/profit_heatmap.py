import os
import matplotlib.pyplot as plt

PLOTS_DIR = "plots"
demand_label = "high"

fig, ax = plt.subplots()
save_path = os.path.join(PLOTS_DIR, f"profit_heatmap_demand{demand_label}.png")
fig.savefig(save_path, dpi=300, bbox_inches="tight")
