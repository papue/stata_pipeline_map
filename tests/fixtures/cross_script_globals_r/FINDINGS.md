# CSG-03 Findings — Cross-script global propagation: R

## Date
2026-04-27

## Summary

R uses `source()` to execute child scripts in the caller's environment, making
variables defined before the `source()` call available inside the sourced script.
The tool currently parses each `.R` file independently with a fresh variable map,
so cross-script variable propagation is not supported.

## Fixture structure

```
run_analysis.R          ← defines ROOT_DIR, OUTPUT_DIR; sources two child scripts
analysis/plot_results.R ← uses ROOT_DIR, OUTPUT_DIR in read_csv / ggsave
analysis/export_tables.R← uses ROOT_DIR, OUTPUT_DIR in read_csv / write_csv
main.R                  ← defines DATA_ROOT; sources pipeline/stage1.R
pipeline/stage1.R       ← uses DATA_ROOT to build STAGE_DIR; sources stage1_process.R
pipeline/stage1_process.R ← uses STAGE_DIR in read_csv / write_csv
```

## Tool output (extract-edges)

```
source,target,command,kind
pipeline/stage1.r,main.r,source,script_call
analysis/plot_results.r,run_analysis.r,source,script_call
analysis/export_tables.r,run_analysis.r,source,script_call
pipeline/stage1_process.r,pipeline/stage1.r,source,script_call
analysis/export_tables.r,{OUTPUT_DIR}/estimates_table.csv,write_csv_readr,placeholder_artifact
analysis/plot_results.r,{OUTPUT_DIR}/estimates_plot.png,ggsave,placeholder_artifact
pipeline/stage1_process.r,{STAGE_DIR}/output.csv,write_csv_readr,placeholder_artifact
```

## Unresolved variables

| Variable   | Defined in          | Used in                                         |
|------------|---------------------|-------------------------------------------------|
| ROOT_DIR   | run_analysis.R      | analysis/plot_results.R, analysis/export_tables.R |
| OUTPUT_DIR | run_analysis.R      | analysis/plot_results.R, analysis/export_tables.R |
| DATA_ROOT  | main.R              | pipeline/stage1.R (to compute STAGE_DIR)         |
| STAGE_DIR  | pipeline/stage1.R   | pipeline/stage1_process.R                        |

## Missing edges

All data-file edges from the sourced scripts are missing because their path
expressions evaluate to placeholder values:

| Expected source edge                     | Expected target edge                       |
|------------------------------------------|--------------------------------------------|
| data/processed/estimates.csv → plot_results.R   | plot_results.R → output/figures/estimates_plot.png |
| data/processed/estimates.csv → export_tables.R  | export_tables.R → output/figures/estimates_table.csv |
| data/stage1/input.csv → stage1_process.R        | stage1_process.R → data/stage1/output.csv |

Read edges are entirely absent (not even as placeholders), because `read_csv`
with a fully-unresolved `file.path()` argument is silently dropped.

## Diagnostics emitted

Three `dynamic_path_partial_resolution` info diagnostics are emitted:
- `analysis/export_tables.r:4`
- `analysis/plot_results.r:7`
- `pipeline/stage1_process.r:2`

No diagnostic is emitted for the missing read-side edges.

## Root cause

`parser/r_extract.py` (or equivalent) builds a per-file variable map and
resolves `file.path()` substitutions only within that file. When a variable
is not defined in the current file, it remains as `{VAR_NAME}` in the resolved
path string, producing a placeholder node instead of a real data path.

There is no mechanism to pass the parent script's variable environment into a
sourced child script before parsing it.
