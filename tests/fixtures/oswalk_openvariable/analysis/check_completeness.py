import os
import re

# -------------------------
# USER SETTINGS
# -------------------------
BASE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "results"
)
OUTPUT_FILE = "completeness_report.txt"
# -------------------------

pattern = re.compile(r"result_(\d+)\.pkl$")
missing_summary = {}

for root, dirs, files in os.walk(BASE_DIR):
    pkl_files = [f for f in files if f.endswith(".pkl")]
    if not pkl_files:
        continue

    found_indices = set()
    for f in pkl_files:
        match = pattern.match(f)
        if match:
            idx = int(match.group(1))
            found_indices.add(idx)

    missing = sorted(set(range(0, 10)) - found_indices)
    missing_summary[root] = missing

with open(OUTPUT_FILE, "w") as out:
    for folder, missing in missing_summary.items():
        out.write(f"Folder: {folder}\n")
        if missing:
            out.write(f"  Missing: {missing}\n")
        else:
            out.write("  All present.\n")
        out.write("\n")

print(f"Done. Report saved to: {OUTPUT_FILE}")
