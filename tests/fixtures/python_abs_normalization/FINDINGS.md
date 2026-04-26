# MO-07 Findings: Python Absolute Path Normalization

## Node ID Mismatch

| Script | Line | Operation | Raw path | Node ID produced |
|--------|------|-----------|----------|-----------------|
| `extraction/extract_data.py` | 7 | write (to_parquet) | `C:\project_external\results\all_results.parquet` | `all_results.parquet` |
| `analysis/generate_graphs.py` | 7 | read (read_parquet) | `__file__`-relative → `../results/all_results.parquet` | `results/all_results.parquet` |
| `analysis/generate_graphs.py` | 8 | read (read_parquet) | `__file__`-relative → `../results/all_results_multiT.parquet` | `results/all_results_multit.parquet` |

## Graph connectivity

The graph is **broken**. The write and reads refer to the same physical file but produce different node IDs:

- Write produces: `all_results.parquet`  (just the filename, absolute base stripped)
- Read produces:  `results/all_results.parquet`  (project-relative via __file__ resolution)

No edge connects `extraction/extract_data.py` → `results/all_results.parquet`.

## Edge CSV (pre-fix)

```
source,target,command,kind
results/all_results.parquet,analysis/generate_graphs.py,read_parquet,reference_input
results/all_results_multit.parquet,analysis/generate_graphs.py,read_parquet,reference_input
extraction/extract_data.py,all_results.parquet,to_parquet,deliverable
```

## Root cause

`_resolve_ospath_join` in `python_extract.py` detects that `path_base` is an absolute-path variable
(`abs_vars`). It strips the absolute base component and returns only the literal suffix parts
(`all_results.parquet`). The result is a bare filename with no directory context.

`to_project_relative` in `model/normalize.py` then receives `all_results.parquet` (not absolute)
and returns it as-is, giving the node ID `all_results.parquet`.

Meanwhile `generate_graphs.py` resolves `__file__` to `analysis/generate_graphs.py`, walks `..`
to `results/`, and builds `results/all_results.parquet` — a proper project-relative path.

## absolute_path diagnostic behaviour

The `absolute_path_usage` warning **is** emitted for line 7 of `extract_data.py`. However,
the node ID `all_results.parquet` is still placed in the graph as an orphan artifact.

## Fix required (MO-08)

When `_resolve_ospath_join` detects an absolute-path variable it should try to locate the
literal suffix parts inside the project tree (e.g. check that `results/all_results.parquet`
exists under `project_root`) and, if found, use that project-relative path as the node ID.
Alternatively, `to_project_relative` can use `os.path.relpath` / filesystem existence checks
to map the suffix back to a canonical project-relative path whenever the raw path has no
directory component but a matching file exists under the project root.
