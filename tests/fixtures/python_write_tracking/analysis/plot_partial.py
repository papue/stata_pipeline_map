import os
import matplotlib.pyplot as plt

def make_plot(plot_type, case_name):
    try:
        _script_dir = os.path.dirname(os.path.abspath(__file__))
    except NameError:
        _script_dir = os.path.join(os.getcwd(), 'analysis')

    plot_name = f"{plot_type} bidding behavior ({case_name})"
    plt.savefig(os.path.join(_script_dir, "plots", f"{plot_name}.png"), dpi=300)
