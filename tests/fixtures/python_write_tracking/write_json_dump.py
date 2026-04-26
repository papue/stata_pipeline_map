import json
import os

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.getcwd()

data = {"key": "value"}
json.dump(data, open(os.path.join(_script_dir, "output", "config.json"), "w"))
