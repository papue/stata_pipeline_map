# MO-09 Findings: R Absolute Path Normalization

## Fixture layout

```
r_abs_normalization/
  extraction/
    extract_data.R       — writes C:/project_external/results/all_results.csv
    extract_parquet.R    — writes file.path("C:/project_external/results", "model_output.parquet")
  analysis/
    analyze.R            — reads file.path(script_dir, "..", "results", "all_results.csv")
    load_model.R         — reads file.path(script_dir, "..", "results", "model_output.parquet")
  results/
    all_results.csv      (empty, exists on disk)
    model_output.parquet (empty, exists on disk)
```

## Node ID table

| File | Role | Raw path | Node ID produced |
|---|---|---|---|
| extraction/extract_data.r | writer | `C:/project_external/results/all_results.csv` | `results/all_results.csv` |
| analysis/analyze.r | reader | `<script_dir>/../results/all_results.csv` | `results/all_results.csv` |
| extraction/extract_parquet.r | writer | `file.path("C:/project_external/results", "model_output.parquet")` | `results/model_output.parquet` |
| analysis/load_model.r | reader | `file.path(<script_dir>, "..", "results", "model_output.parquet")` | `results/model_output.parquet` |

## Edges produced

```
source,target,command,kind
results/all_results.csv,analysis/analyze.r,read_csv,generated_artifact
results/model_output.parquet,analysis/load_model.r,read_parquet,generated_artifact
extraction/extract_data.r,results/all_results.csv,write_csv,deliverable
extraction/extract_parquet.r,results/model_output.parquet,write_parquet,deliverable
```

## Analysis

**Node IDs match.** Writer and reader for both data files produce the identical project-relative node ID, so the graph is fully connected (one component per data file, not two separate components).

### How the R parser resolves absolute write paths

The writer (`extract_data.R`) stores `output_path <- "C:/project_external/results/all_results.csv"` as a literal string variable. The R extractor expands that variable before pattern-matching, then calls `to_project_relative()` with the absolute path.

`to_project_relative()` (in `model/normalize.py`) handles this via `_infer_existing_project_suffix`: it walks the suffix parts of the absolute path (`results/all_results.csv`, then `all_results.csv`) and checks whether each suffix exists under `project_root`. Since `results/all_results.csv` exists, it is returned directly.

### How the R parser resolves script-relative read paths

The reader (`analyze.R`) uses `dirname(sys.frame(1)$ofile)` — the R equivalent of `__file__`. The R extractor recognises this idiom (`_SCRIPT_DIR_RE`) and seeds `script_dir` with the absolute path of the script's parent directory. `file.path(script_dir, "..", "results", "all_results.csv")` is then joined and the `..` segment resolved by `_add_event`, producing the same `results/all_results.csv` node ID.

## MO-10 conclusion

**No fix required for `r_extract.py`.** The R parser already correctly normalises absolute-path writes to project-relative node IDs via `_infer_existing_project_suffix` in `normalize.py`. This is structurally different from the Python bug fixed in MO-08, where bare filenames (just `all_results.csv`) were not resolved to their project-relative path. In the R case the full suffix `results/all_results.csv` is present in the absolute path, so the suffix-walking logic finds the match without needing an rglob fallback.
