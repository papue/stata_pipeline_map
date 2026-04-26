from pathlib import Path
import matplotlib.pyplot as plt

base = Path(__file__).parent
out = base / "plots" / "direct.png"
plt.savefig(out, dpi=300)
