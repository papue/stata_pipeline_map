import os

ENV_PATH = os.environ.get("CONFIG_PATH")  # runtime
full_path = "/" + ENV_PATH + "/config.yaml"
with open(full_path) as f:
    pass
