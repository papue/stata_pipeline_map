import pickle
import os

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.getcwd()

model = {"weights": [1, 2, 3]}
pickle.dump(model, open(os.path.join(_script_dir, "output", "model.pkl"), "wb"))
