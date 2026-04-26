from pathlib import Path
import pandas as pd

base = Path(__file__).parent.parent / "output"
df = pd.DataFrame({"x": [1, 2]})
df.to_csv(base / "results.csv")
