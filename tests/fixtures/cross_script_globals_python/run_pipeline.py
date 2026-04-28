import subprocess

DATA_ROOT = "data"
OUTPUT_ROOT = "output"

subprocess.run(["python", "analysis/stage1.py", "--data", DATA_ROOT, "--out", OUTPUT_ROOT])
subprocess.run(["python", "analysis/stage2.py", "--data", DATA_ROOT, "--out", OUTPUT_ROOT])
