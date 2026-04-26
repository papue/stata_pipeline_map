import os
import matplotlib.pyplot as plt

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.path.join(os.getcwd(), 'analysis')

def save_figure(fig, output_path=None):
    if output_path:
        fig.savefig(output_path, dpi=300)

out1 = os.path.join(_script_dir, "plots", "fig_a.png")
out2 = os.path.join(_script_dir, "plots", "fig_b.png")
fig, ax = plt.subplots()
save_figure(fig, output_path=out1)
save_figure(fig, output_path=out2)
