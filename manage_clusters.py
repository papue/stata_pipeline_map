from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from data_pipeline_flow.wizard import manage_clusters_interactive

if __name__ == '__main__':
    raise SystemExit(manage_clusters_interactive(ROOT))
