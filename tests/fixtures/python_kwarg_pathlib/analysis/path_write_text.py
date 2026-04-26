from pathlib import Path
import json

out = Path(__file__).parent / "data" / "config.json"
out.write_text(json.dumps({"key": "value"}))
