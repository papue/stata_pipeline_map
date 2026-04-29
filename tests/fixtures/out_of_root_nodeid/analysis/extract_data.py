import os
import pandas as pd

# Absolute path outside project_root — simulated with a drive-rooted path
# Use a path that is guaranteed to be outside the fixture dir.
# We use os.path.abspath to construct it relative to __file__ going up TWO levels.
_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'results_store'))
save_path = os.path.join(_root, 'all_results.parquet')

df = pd.DataFrame({'x': [1, 2, 3]})
df.to_parquet(save_path, index=False)
