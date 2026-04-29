# Out-of-root node ID mismatch — findings

## Confirmed disconnected nodes

| Script | Code pattern | Node ID produced |
|--------|-------------|-----------------|
| extract_data.py | abs path via `_root` (os.path.abspath + os.path.join going 2 levels up then `results_store/`) | **no edge produced** (write path not captured; script becomes orphan) |
| generate_graphs.py | `__file__` + `../../results_store` via `_script_dir` | `results_store/all_results.parquet` |

## Are the two IDs different? Yes
`extract_data.py` produced **no data node at all** for its write. `generate_graphs.py` produced `results_store/all_results.parquet`.
The data node exists only from the read side.

## Is there a connecting edge between the two scripts? No
There is no edge from `extract_data.py` to any data node. The only edge in the graph is:
```
results_store/all_results.parquet → analysis/generate_graphs.py  (read_parquet)
```
`extract_data.py` has zero edges and is flagged as an orphan.

## Full edge CSV
```
source,target,command,kind
results_store/all_results.parquet,analysis/generate_graphs.py,read_parquet,reference_input
```

## Diagnostics observed
- `orphan_node`: Yes — `analysis/extract_data.py` has no incoming or outgoing edges
- `missing_referenced_file`: Yes — `results_store/all_results.parquet` does not exist in project tree (as expected; it is outside root)
- `ambiguous_name`: No
- `absolute_path_usage`: No (not reported as a diagnostic code)

## Graph nodes (from snapshot-json)
1. `analysis/extract_data.py` (script, orphan)
2. `analysis/generate_graphs.py` (script)
3. `results_store/all_results.parquet` (artifact, reference_input)

## Root cause confirmed

The write side in `extract_data.py` uses a deeply-nested dynamic path:
```python
_root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'results_store'))
save_path = os.path.join(_root, 'all_results.parquet')
```
The parser traces `__file__` resolution for `_script_dir`-style patterns but the chain here goes through `_root` as an intermediate variable. The resolved absolute path points outside `project_root` (two levels up). The Python parser either fails to resolve the chain fully or produces no path token for the `to_parquet` call.

The read side in `generate_graphs.py` uses `_script_dir` (which the parser recognizes as a `__file__`-relative base) + `../../results_store`. The parser resolves this relative to the script's location, yielding a path two levels above the script (`analysis/`) and one above `project_root`, then normalizes it. `_infer_existing_project_suffix` in `normalize.py` (line 135) matches the trailing `results_store/all_results.parquet` suffix against the project tree and returns `results_store/all_results.parquet` as the node ID — which is actually a relative path inside the project root even though the physical file is outside it.

Key functions in `model/normalize.py`:
- `to_project_relative` — lines 107–142
- `_infer_existing_project_suffix` — lines 89–103; returns `None` when no suffix match found
- Fallback at line 142: returns raw normalized path (full absolute string) when `_infer_existing_project_suffix` returns `None`

**Net effect**: The write from `extract_data.py` produces no edge (path resolution silently drops it). The read from `generate_graphs.py` produces a node ID `results_store/all_results.parquet` via the `_infer_existing_project_suffix` heuristic. Since no write edge exists for `extract_data.py`, the two scripts are not connected, and the pipeline flow is invisible to the tool.
