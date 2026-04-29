import os
import matplotlib.pyplot as plt
import pandas as pd

_script_dir = os.path.dirname(os.path.abspath(__file__))
data_path = os.path.join(_script_dir, '..', 'results')
df = pd.read_parquet(os.path.join(data_path, 'all_results.parquet'))


def get_boxplot(df, col):
    # --- Compute statistics ---
    mean = df[col].mean()
    std = df[col].std()
    median = df[col].median()

    # --- Draw box ---
    fig, ax = plt.subplots()
    ax.boxplot(df[col])
    ax.set_title(f"{col}: mean={mean:.2f}")
    return fig, ax


def get_boxplot_2(df, col):
    # --- Compute statistics ---
    q1 = df[col].quantile(0.25)
    q3 = df[col].quantile(0.75)

    # --- Draw box ---
    fig, ax = plt.subplots()
    ax.boxplot(df[col])
    return fig, ax


## testing
# fig, ax = get_boxplot(df, 'value')
# plt.show()


def plot_trajectories(df):
    fig, ax = plt.subplots()

    # --- Modern Nord-Style Colours ---
    colours = ['#88C0D0', '#81A1C1', '#5E81AC']

    # --- Price trajectories ---
    for i, col in enumerate(df.columns[:3]):
        ax.plot(df[col], color=colours[i], label=col)

    # --- Quantity effect curves ---
    ax2 = ax.twinx()
    ax2.plot(df.iloc[:, 3], linestyle='--')

    # --- Quantity effect areas ---
    ax2.fill_between(range(len(df)), 0, df.iloc[:, 3], alpha=0.2)

    # --- Formatting ---
    ax.set_xlabel("Period")
    ax.legend()
    plt.tight_layout()
    return fig


for case in ["baseline", "treatment"]:
    fig, ax = get_boxplot(df, 'value')
    plt.savefig(os.path.join(_script_dir, '..', 'output', f'{case}_boxplot.png'))
    plt.close()
