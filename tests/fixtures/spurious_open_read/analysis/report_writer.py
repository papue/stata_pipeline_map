import os

# Module-level string constants for output paths
OUTPUT_FILE = "summary_report.txt"
LOG_FILE = "processing.log"

# Also test with os.path.join — variable-built path
output_dir = "reports"
DETAIL_FILE = os.path.join(output_dir, "details.txt")

data = {"item1": 42, "item2": 99}

# Pattern 1: simple string constant
with open(OUTPUT_FILE, "w") as out:
    for key, val in data.items():
        out.write(f"{key}: {val}\n")

# Pattern 2: append mode — also a write, not a read
with open(LOG_FILE, "a") as log:
    log.write("Processing complete.\n")

# Pattern 3: variable-built path, write mode
with open(DETAIL_FILE, "w") as detail:
    detail.write("Details here.\n")

# Pattern 4: explicit read (should produce read edge, not write)
with open("config.txt", "r") as cfg:
    settings = cfg.read()

print(f"Reports written to: {OUTPUT_FILE}, {LOG_FILE}, {DETAIL_FILE}")
