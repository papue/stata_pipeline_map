import os
import matplotlib.pyplot as plt

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.path.join(os.getcwd(), 'analysis')

def plot_and_save(data, filename=None):
    fig, ax = plt.subplots()
    ax.plot(data)
    if filename is not None:
        from pathlib import Path
        p = Path(filename)
        p.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(p, dpi=300)

plot_and_save([1, 2, 3], filename=os.path.join(_script_dir, "plots", "price_avg.png"))
plot_and_save([4, 5, 6], filename=os.path.join(_script_dir, "plots", "quantity_avg.png"))
plot_and_save([7, 8, 9], filename=os.path.join(_script_dir, "plots", "benchmark.png"))
