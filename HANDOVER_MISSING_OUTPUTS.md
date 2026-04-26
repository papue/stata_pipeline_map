# Parser Handover: Undetected Write Paths and Remaining Graph Issues

## Context

This handover describes the remaining parser gaps found after the dynamic path improvements
in `HANDOVER_DYNAMIC_PATHS.md` were applied. All patterns are from `*.py` scripts in the
same real Python research project. The result is that most output figures (PNG/PDF) are
missing from the dependency graph entirely, and two nodes that represent the same physical
file on disk appear as separate disconnected nodes.

The project root is `01 data work/`. Scripts live in `analysis/`, outputs in `analysis/plots/`
and a sibling `output/` folder outside the project root.

---

## Current detection state per script

This table shows what the parser currently detects vs. what exists in the code, to allow
the coding agent to reproduce and verify each gap.

| Script | Read edges detected | Write edges detected | Expected write edges |
|--------|--------------------|--------------------|----------------------|
| `generate_graphs.py` | `results/all_results.parquet` ✓, `results/all_results_multit.parquet` ✓ | 2 of ~8 PNG outputs (only literal-name ones) | ~8 PNG files in `analysis/plots/` |
| `generate_graphs_k0.py` | `results/all_results.parquet` ✓ | 2 of ~6 PNG outputs | ~6 PNG files in `analysis/plots/` |
| `generate_output.py` | `results/all_results.parquet` ✓ | **0** | Many PDF files in `output/{case}/` |
| `random_action_check.py` | `results/all_results.parquet` ✓ | **0** | 7 PNG files in `analysis/plots/` |
| `profit_heatmap.py` | `parameters/parameter_demand_benchmark_{df_name}.json` ✓ | 1 of 2 PNG outputs (the `_relative` variant is missed) | 2 PNG files per demand factor in `analysis/plots/` |
| `merit_order_plot.py` | **0** (reads inline data — no file reads) | **0** | 1 PNG file in `output/` |
| `run_simulation.py` | Spurious `.` node (JSON read partially resolved — see Issue 6) | — | Should produce `{PATH_PARAMETERS}.json` placeholder or be dropped |

---

## Issue 1 — Write paths via variable not tracked (`savefig(var)`, `to_parquet(var)`)

### Affected scripts
All analysis scripts — see table above.

### Description
The variable tracker added in the previous round resolves variables at **read** call sites
(`pd.read_parquet(var)`, `open(var)`). The same logic is not applied to **write** call sites
(`fig.savefig(var)`, `plt.savefig(var)`, `df.to_parquet(var)`, `df.to_csv(var)`).
Any path stored in a variable and then passed to a write function is silently dropped.

### Exact code — `generate_graphs.py` (fully resolvable case)
```python
# _script_dir is resolved via __file__ (Pattern 1 from previous handover)
plot_name = "Market prices (green) and avg quantity bids under different MRP"
plt.savefig(os.path.join(_script_dir, "plots", f"{plot_name}.png"), dpi=300, bbox_inches="tight")
```
`plot_name` is a string literal assigned one line before. The full path is statically
resolvable to `analysis/plots/Market prices (green) and avg quantity bids under different MRP.png`.
Currently: **not detected** because the parser does not track `plot_name` as a path variable.

### Exact code — `generate_output.py` (zero outputs currently detected)
```python
output_path = r"D:\Sciebo New\electricity_qlearning\AlgorithmicElectricityAuctions\output"

case_folder = os.path.join(output_path, case)           # `case` is a loop variable
filename = f"{case}_alpha{ialpha}_nu{inu}_{metric}.pdf"  # all parts are loop variables
filepath = os.path.join(case_folder, filename)
fig.savefig(filepath, format='pdf', bbox_inches='tight')
```
`output_path` is a trackable absolute string literal. `case_folder` and `filepath` are
chained variables. Currently: **0 write edges detected** from this script — it appears as a
dead-end node with only an incoming read edge.

### Exact code — `merit_order_plot.py` (zero inputs and zero outputs currently detected)
```python
output_path = r"D:\Sciebo New\electricity_qlearning\AlgorithmicElectricityAuctions\output"
save_path = output_path + r"\merit_order.png"   # string concatenation, not os.path.join
fig.savefig(save_path, dpi=300, bbox_inches="tight")
```
Currently: **0 edges detected in either direction** — the script appears as a completely
isolated orphan node.

### Expected behaviour
Apply the same variable-tracking logic to write call sites as already exists for reads.
When a path is fully resolvable, emit a concrete write edge. When partially resolvable,
emit a placeholder node (see Issue 2).

---

## Issue 2 — Placeholder nodes not emitted for partially-resolved write paths

### Description
When a read path is only partially resolvable (e.g. one component is a loop variable),
the parser already emits a placeholder node such as
`analysis/plots/profit_heatmap_demand{demand_label}.png`. The same behaviour is **not**
implemented for write paths. If any component of a write path is unresolvable, the whole
edge is silently dropped instead of emitting a `{var_name}` placeholder.

### Exact code — `generate_graphs.py` (partially resolvable — function argument)
```python
plot_name = f"{plot_type} bidding behavior ({case_name})"  # both are function arguments
plt.savefig(os.path.join(_script_dir, "plots", f"{plot_name}.png"), dpi=300, bbox_inches="tight")
```
`_script_dir` resolves to `analysis/`. `plot_type` and `case_name` are unresolvable function
parameters. Expected placeholder node: `analysis/plots/{plot_type} bidding behavior ({case_name}).png`
or simply `analysis/plots/{plot_name}.png`.

### Exact code — `generate_graphs.py` (partially resolvable — f-string with argument)
```python
plot_name = f"{treatment} bids under different {market} market scenarios"
fig.savefig(os.path.join(_script_dir, "plots", f"{plot_name}.png"), dpi=300, bbox_inches="tight")
```
Expected: `analysis/plots/{treatment} bids under different {market} market scenarios.png`.

### Complete list of savefig calls in `generate_graphs.py` and their current detection status

| `plot_name` value | Resolvable? | Currently detected? |
|---|---|---|
| `"Market prices (green) and avg quantity bids under different MRP"` | Yes — literal | No |
| `"Share of undersupplied markets under different MRP"` (+ conditional `" simple"` suffix) | Partially — base is literal | No |
| `f"{plot_type} bidding behavior ({case_name})"` | No — function args | No |
| `f"{treatment} bids under different {market} market scenarios"` | No — function args | No |
| `f"{label_base}s under {treatment} market scenarios"` | No — function args | No |
| `f"Price and quantity effect ({case_name})"` | No — function args | No |
| `f"Price effect depending on {treatment}"` | No — function args | No |
| `f"Share strict price hierarchy ({treatment})"` | No — function args | No |
| `f"Share all prices equal ({treatment})"` | No — function args | No |

Note: `title` variable is used in one call (`fig.savefig(..., f"{title}.png")`). `title` is
set earlier in the same function — whether it is resolvable depends on whether it is a literal
or argument.

### Exact code — `generate_output.py` (partially resolvable — chained variables)
```python
filename = f"{case}_alpha{ialpha}_nu{inu}_{metric}.pdf"  # all loop variables
filepath = os.path.join(case_folder, filename)
fig.savefig(filepath, ...)
```
Expected placeholder: `output/{case}/{case}_alpha{ialpha}_nu{inu}_{metric}.pdf`
(after `output_path` absolute base is resolved via Issue 3 normalisation).

### Exact code — `profit_heatmap.py` (second savefig — currently fully missed)
```python
PLOTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plots")  # → analysis/plots/
rel_save_path = os.path.join(PLOTS_DIR, f"profit_heatmap_demand{demand_label}_relative.png")
plot_heatmap(rel_heatmap, df_name, rel_save_path, show_colorbar=False)
# (plot_heatmap calls fig.savefig(save_path) internally)
```
The first call (`profit_heatmap_demand{demand_label}.png`) is already detected. The second
(`_relative` variant) is completely missed because the path is passed as a positional
argument through a user-defined function. Expected: `analysis/plots/profit_heatmap_demand{demand_label}_relative.png`.

### Expected behaviour
Extend placeholder logic from reads to writes:
- Resolve as much of the path as possible.
- Any remaining unresolved variable component stays as `{var_name}` in the node ID.
- Emit the write edge with the partially-resolved path.

---

## Issue 3 — Absolute path and `__file__`-relative path produce two node IDs for the same file

### Description
When one script writes a file using an absolute path and another reads it using a
`__file__`-relative path that resolves to the same physical location, the parser creates
two separate nodes with different IDs. This breaks the Extraction → Analysis connection
in the graph.

### Current observable symptom
In the rendered pipeline, the Extraction cluster (`extract_data.py`) and the Analysis
cluster (`generate_graphs.py`, `generate_output.py`, etc.) are **disconnected**. Two
separate `all_results.parquet` nodes appear in the graph:
- `all_results.parquet` — produced by the write side (absolute path, incorrectly normalized)
- `results/all_results.parquet` — consumed by the read side (`__file__`-relative)

### Exact code — write side (`extract_data.py`)
```python
path_base = r"D:\Sciebo New\electricity_qlearning\AlgorithmicElectricityAuctions\results"
save_path = os.path.join(path_base, "all_results.parquet")
df_results.to_parquet(save_path, index=False)
```
Parser currently produces node ID: `all_results.parquet` (only the bare filename).
Physical location: `<project_parent>/results/all_results.parquet`.

### Exact code — read side (`generate_graphs.py`)
```python
_script_dir = os.path.dirname(os.path.abspath(__file__))   # → <project_root>/analysis/
data_path = os.path.join(_script_dir, '..', 'results') + os.sep
df_results = pd.read_parquet(f"{data_path}all_results.parquet")
```
Parser correctly produces node ID: `results/all_results.parquet`.

### Root cause
The absolute-path normalisation strips the drive/prefix but does not compute the correct
path relative to `project_root`. Both paths refer to the same file, but produce different
node IDs.

### Expected behaviour
When an absolute path is encountered, compute its path relative to `project_root`:
1. If inside `project_root`: strip prefix → use as relative node ID.
2. If outside `project_root` (e.g. sibling folder): `os.path.relpath(abs_path, project_root)`
   → normalize `..` traversals with the same logic as `__file__`-relative resolution.
   Result must match the node ID the read-side resolver would produce for the same file.
3. If on a different drive or completely unrelated: emit `absolute_path` diagnostic but
   still create the node.

**Key invariant: two code paths resolving to the same physical file must produce the same node ID.**

---

## Issue 4 — String concatenation (`+`) not recognised as path join

### Description
The parser recognises `os.path.join(var, literal)` for path construction but does not
recognise `var + r"\literal"` or `var + "/literal"`.

### Exact code — `merit_order_plot.py`
```python
output_path = r"D:\Sciebo New\electricity_qlearning\AlgorithmicElectricityAuctions\output"
save_path = output_path + r"\merit_order.png"
fig.savefig(save_path, dpi=300, bbox_inches="tight")
```
`save_path` is never resolved. If it were, the parser would produce (after Issue 3
normalisation) `../output/merit_order.png` relative to project root.

Note: `merit_order_plot.py` has **no read edges either** — it builds its data from inline
NumPy arrays with no file reads. The only missing edge is this single write.

### Expected behaviour
In the variable tracker, recognise `BinOp(Add)` AST nodes where at least one operand is a
known path string. Treat `a + b` as path join equivalent to `os.path.join(a, b)`,
handling separator differences between `"/"` and `r"\"`.

---

## Issue 5 — Paths passed as keyword arguments to a helper function not tracked

### Description
`random_action_check.py` currently has **zero write edges** in the graph even though all
its output paths are fully statically resolvable. The reason is that the script passes
resolved paths as keyword arguments (`filename=...`) to a user-defined plotting helper,
which internally calls `plt.savefig(path)`. The parser does not follow the argument into
the function body.

### Exact code — `random_action_check.py`
```python
def plot_avg_market_prices(..., filename=None, ...):
    ...
    if filename is not None:
        path = Path(filename)          # pathlib.Path wrapping not unwrapped by parser
        path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(path, dpi=300, bbox_inches="tight")

# Call sites — all filenames are fully resolvable __file__-relative literals:
plot_avg_market_prices(
    ...,
    filename=os.path.join(_script_dir, "plots", "avg_market_price_vs_demand.png")
)
plot_avg_market_prices(
    ...,
    filename=os.path.join(_script_dir, "plots", "random_action_benchmark.png")
)
# ... 5 more call sites
```

### All 7 expected write edges (currently all missing)
```
analysis/plots/avg_market_price_vs_demand.png
analysis/plots/random_action_benchmark.png
analysis/plots/random_action_mrp_high.png
analysis/plots/random_action_capacity_high.png
analysis/plots/price_bids_random_vs_data_benchmark.png
analysis/plots/price_bids_random_vs_data_capacity_high.png
analysis/plots/price_bids_random_vs_data_mrp_high.png
```

### Why it is missed
Two compounding gaps:
1. `pathlib.Path(var)` is not unwrapped — the parser does not recognise `Path(filename)`
   as equivalent to `filename` for path tracking.
2. The `filename` keyword argument at the call site is not propagated into the function body.

### Suggested fix (pragmatic — avoids full inter-procedural analysis)
At each call site where a keyword argument matching a known "path parameter name"
(`filename`, `path`, `output`, `save_path`, `filepath`) is passed with a resolvable value,
and the called function is user-defined (not a stdlib/third-party function), emit a write
edge directly from the call site to the resolved path. Do not enter the function body.

Additionally, treat `Path(var)` and `pathlib.Path(var)` as transparent wrappers — wherever
the variable tracker would resolve `var`, resolve `Path(var)` to the same path string.

---

## Issue 6 — Spurious "." node from partial resolution of JSON read with string concatenation

### Description
A spurious node with ID `.` appears in the pipeline graph, connected to `run_simulation.py`.
It is created by partially resolving a path that reads a JSON parameter file, where the
filename is built by concatenating `"./"` with a runtime variable.

### Exact code — `run_simulation.py`
```python
with open("./" + PATH_PARAMETERS + ".json") as f:
    parameters = json.load(f)
```
`PATH_PARAMETERS` is a command-line argument (runtime value, not statically resolvable).
The parser resolves the `"./"` string literal prefix, cannot resolve `PATH_PARAMETERS`,
and emits the partial result `"."` as a node ID. The result is a meaningless dot node
connected to `run_simulation.py` in the graph.

### Expected behaviour
Two options:
1. **Drop the edge**: when the resolved portion of a concatenation is only a directory
   prefix (ends with `/` or `.` or `./`) with no filename component, do not emit a node.
2. **Emit a placeholder**: treat the unresolved middle segment as a variable placeholder
   and emit `{PATH_PARAMETERS}.json` as the node ID (discarding the `./` prefix since it
   adds no information).

Option 2 is preferable as it preserves the information that a JSON parameter file is read.

---

## Issue 7 — JSON-derived path: output filename depends on value read from a JSON input

### Description
In `profit_heatmap.py`, the output filename is not a static string — it is derived from a
value (`demand_label`) obtained by reading the JSON parameter file at runtime. This creates
a chain where a read feeds into an output path, which the parser cannot statically resolve
even in principle.

### Exact code — `profit_heatmap.py`
```python
def _read_inflexible_demand(df_name: str) -> str:
    """Return inflexible demand as display string, read from the parameter JSON."""
    param_file = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..", "parameters", f"parameter_demand_benchmark_{df_name}.json"
    )
    with open(param_file) as f:
        params = json.load(f)
    demand = params["inflexible_demand_pp"]
    return str(demand[0] if isinstance(demand, list) else demand)

for df_name in DEMAND_FACTORS:
    demand_label = _read_inflexible_demand(df_name)   # runtime value from JSON
    save_path = os.path.join(PLOTS_DIR, f"profit_heatmap_demand{demand_label}.png")
    plot_heatmap(heatmap, df_name, save_path, show_colorbar=False)
```

### Current detection state
- Input `parameters/parameter_demand_benchmark_{df_name}.json` — detected with `{df_name}`
  placeholder ✓ (but detected at module scope, not inside the helper function — unclear
  if this is correct or fragile)
- Output `analysis/plots/profit_heatmap_demand{demand_label}.png` — **partially** detected:
  the first call is shown, the second (`_relative` variant) is not
- `demand_label` is a return value from a function that reads a JSON file — it cannot be
  resolved statically, so `{demand_label}` as placeholder is correct and acceptable

### Expected behaviour
The parser should accept `{demand_label}` as a valid placeholder for the output node.
The second savefig (Issue 2) should emit `analysis/plots/profit_heatmap_demand{demand_label}_relative.png`.
No further resolution of `demand_label` is expected.

---

## Summary Table

| Issue | Scripts affected | Currently visible symptom | Difficulty |
|-------|-----------------|--------------------------|------------|
| 1 — Variable tracking not applied to write call sites | `generate_graphs.py`, `generate_output.py`, `merit_order_plot.py` | Write edges silently dropped; scripts appear as dead-ends or orphans | Low — mirror existing read logic |
| 2 — No placeholder nodes for partial write paths | `generate_graphs.py`, `generate_graphs_k0.py`, `generate_output.py`, `profit_heatmap.py` | Most output figures completely absent from graph | Low — mirror existing read placeholder logic |
| 3 — Absolute vs `__file__`-relative paths → two node IDs for same file | `extract_data.py` ↔ all analysis scripts | Extraction and Analysis clusters are disconnected; duplicate `all_results.parquet` nodes | Medium — requires relpath from project root |
| 4 — String concatenation (`+`) not recognised as path join | `merit_order_plot.py` | `merit_order.png` write not detected | Low — add `BinOp(Add)` case |
| 5 — Keyword-arg paths not tracked; `pathlib.Path()` not unwrapped | `random_action_check.py` | **All 7 write edges missing**; script is a dead-end | Medium — pragmatic call-site heuristic |
| 6 — Spurious `.` node from partial JSON path resolution | `run_simulation.py` | Meaningless `.` node appears in Simulation cluster | Low — drop or replace with placeholder |
| 7 — Output filename derived from JSON value at runtime | `profit_heatmap.py` | Acceptable — `{demand_label}` placeholder is correct; second savefig still missing (Issue 2) | Not fixable beyond placeholder; covered by Issue 2 |

---

## Suggested Regression Fixtures

```
tests/fixtures/python_write_paths/
    savefig_literal_var.py      # plot_name = "literal"; plt.savefig(os.path.join(dir, f"{plot_name}.png"))
    savefig_partial_var.py      # plot_name = func_arg; plt.savefig(os.path.join(dir, f"{plot_name}.png"))
    savefig_absolute_chain.py   # output_path = r"C:\abs\path"; case_folder = os.path.join(output_path, case); filepath = os.path.join(case_folder, "fig.pdf"); fig.savefig(filepath)
    savefig_str_concat.py       # output_path = r"C:\abs\path"; save_path = output_path + r"\fig.png"; fig.savefig(save_path)
    savefig_kwarg_helper.py     # def plot(..., filename=None): path = Path(filename); plt.savefig(path)
                                # called as: plot(filename=os.path.join(_script_dir, "plots", "fig.png"))
    open_dotslash_json.py       # open("./" + RUNTIME_VAR + ".json")
    data/fig.pdf                # (empty)
    data/fig.png                # (empty)

tests/fixtures/python_abs_normalization/
    writer.py                   # path_base = r"<abs_path>/results"; save_path = os.path.join(path_base, "data.parquet"); df.to_parquet(save_path)
    reader.py                   # _script_dir = os.path.dirname(os.path.abspath(__file__)); pd.read_parquet(os.path.join(_script_dir, "..", "results", "data.parquet"))
    results/data.parquet        # (empty)
```

Each fixture should assert:
- The expected node IDs are produced
- Writer and reader share the same node ID for the same physical file (Issue 3)
- Placeholder nodes appear for unresolvable components rather than edges being dropped (Issues 2, 6)
- `pathlib.Path(var)` is treated transparently (Issue 5)
