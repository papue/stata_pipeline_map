import numpy as np
import os

try:
    _script_dir = os.path.dirname(os.path.abspath(__file__))
except NameError:
    _script_dir = os.getcwd()

arr = np.array([1, 2, 3])
np.save(os.path.join(_script_dir, "output", "array.npy"), arr)
np.savetxt(os.path.join(_script_dir, "output", "array.txt"), arr)
