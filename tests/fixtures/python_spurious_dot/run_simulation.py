import json
import sys

PATH_PARAMETERS = sys.argv[1]  # runtime — not statically resolvable

with open("./" + PATH_PARAMETERS + ".json") as f:
    parameters = json.load(f)
