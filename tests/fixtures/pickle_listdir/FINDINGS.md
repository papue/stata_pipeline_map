# pickle.load + os.listdir missing read edges — findings

## Pattern results

| Script | Pattern | Edge present? | Node ID (if any) |
|--------|---------|--------------|-----------------|
| extract_data.py | one-line pickle.load(open(..., "rb")) | NO | — |
| extract_data.py | two-line with open(..., "rb") + pickle.load | NO | — |
| extract_data.py | json.load (text read, should work) | NO | — |
| extract_data.py | os.listdir loop + pickle | NO | — |
| profit_heatmap.py | load_pkl_files helper + os.listdir | NO | — |

## Tool output summary

- `extract-edges` produced a header-only CSV (zero data rows; zero edges total).
- `validate` produced 6 diagnostics:
  - `[warning] orphan_node` for `analysis/extract_data.py`
  - `[warning] orphan_node` for `analysis/profit_heatmap.py`
  - `[warning] empty_graph` — Graph has no edges.
  - `[info] excluded_files` — 1 file excluded (viewer_output/); irrelevant to these scripts.
  - `[info] project_scan` — 2 Python files found, 0 Stata, 0 R.
  - `[info] excluded_path_inventory` — 1 excluded path recorded.

## Root cause confirmed

### pickle.load

The `_FIXED_READ_PATTERNS` list in `python_extract.py` (line 285) includes a `pickle_load` regex:

```
r'\bpickle\.load\s*\(\s*open\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')'
```

This regex **only fires when a literal string appears directly as the first argument of the inner `open()` call**. In both fixture scripts the path is built dynamically via `os.path.join(...)`, so the capture groups match nothing and no read edge is emitted.

- Pattern 1 (`pickle.load(open(os.path.join(path, "result_0.pkl"), "rb"))`): the first argument of `open` is `os.path.join(...)`, not a quoted literal → no match.
- Pattern 2 (`with open(files[0], "rb") as f: data = pickle.load(f)`): `open` receives a variable (`files[0]`) → no literal string to capture; `pickle.load(f)` also does not match `pickle\.load\s*\(\s*open` → no match.
- `load_pkl_files` in `profit_heatmap.py`: same two-line form with `os.path.join(folder, fname)` → no match.

### json.load (baseline)

The `json_load` regex (line 286) has the same structure — it also requires a literal string directly inside `open()`. In `extract_data.py` the `json.load` call uses `open(param_path, "r")` where `param_path = os.path.join(path, "parameters.json")` is a variable → **no edge produced**.

> Conclusion: even the "should already work" json.load baseline produces NO edge here because the path is dynamic.

### open(..., "rb") binary mode

The `open_read` regex (line 284) does match `"rb"` mode (the optional mode group covers `r[bt]?`), so binary-mode opens are not intentionally excluded. The problem is purely that all paths are dynamic (variables, not literals).

### os.listdir

`os.listdir(folder)` is not recognised as a read event anywhere in `python_extract.py` or `multi_extract.py`. There is no regex for `os.listdir`, `glob.glob`, or directory-scan idioms. The pattern is invisible to the parser.

## Verdict

All five patterns produce **zero read edges** because:
1. The parser requires a **literal string** to appear directly as the path argument; `os.path.join(...)` expressions are dynamic and unresolvable at parse time.
2. `os.listdir` is not in any read command set.
3. The two-line `with open(var, "rb") as f: pickle.load(f)` form is not matched by the `pickle_load` regex (which only handles the one-line inline form).
