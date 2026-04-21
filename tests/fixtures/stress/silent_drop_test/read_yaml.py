import yaml
import pandas as pd

# This will emit open_read (matched by open() pattern)
config = yaml.safe_load(open("input/settings.yaml"))

# This will emit read_csv (pandas read)
df = pd.read_csv("input/data.csv")
