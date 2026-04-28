# fstring_path direction bug — Python replication findings

## Confirmed wrong-direction edges

| Script | Pattern | Expected from→to | Actual from→to |
|--------|---------|-----------------|----------------|
| `generate_output.py` | Two-line: `filepath = f"results/{filename}"` then `fig.savefig(filepath, ...)` | `generate_output.py` → `*_alpha*_nu*_*.pdf` | `*_alpha*_nu*_*.pdf` → `analysis/generate_output.py` |
| `profit_heatmap.py` | Two-line: `save_path = os.path.join(PLOTS_DIR, f"...{demand_label}.png")` then `fig.savefig(save_path, ...)` | `profit_heatmap.py` → `profit_heatmap_demand*.png` | `profit_heatmap_demand*.png` → `analysis/profit_heatmap.py` |

## Confirmed missing edges (no edge at all)

| Script | Pattern | Expected edge |
|--------|---------|--------------|
| `generate_graphs.py` | Inline `os.path.join(..., f"{plot_name}.png")` inside `savefig(...)` | `fstring_path` edge missing entirely — the `savefig` regex fires first and emits a `savefig`-kind edge instead |

## Additional observations

- `generate_graphs.py` does produce a **correct-direction** edge (`generate_graphs.py` → `analysis/plots/baseline.png`) via the `savefig` command kind, so the output isn't wrong — but it is produced by a different code path (the savefig regex, not fstring_path). The f-string variable is resolved to its literal value `baseline`.
- `profit_heatmap.py` produces **two** edges: one wrong-direction `fstring_path` edge AND one `savefig` edge where the variable `{demand_label}` is not interpolated (it appears literally as `profit_heatmap_demand{demand_label}.png`).
- `generate_output.py` produces only the wrong-direction `fstring_path` edge; no `savefig` edge is produced (because `savefig` is on a separate line from the f-string).

## Root cause confirmed

- `fstring_path` is NOT in `_PYTHON_READ_CMDS` or `_PYTHON_WRITE_CMDS` in `multi_extract.py` — confirmed by the handover document. According to the handover, it falls through the routing logic and is silently dropped at line 269. But the edges CSV shows `fstring_path` edges ARE emitted (with wrong direction), so either the routing has been partially updated or there is a separate code path.
- The `is_write` flag computed in `python_extract.py` is not propagated to `multi_extract.py` because `ParsedEvent` has no `is_write` field.
- Two-line pattern: `is_write` is never set because `savefig` is not on the same line as the f-string assignment; the f-string line only has an assignment, which is not a write signal.
- Same-line `os.path.join` case: the `savefig` regex fires correctly on the full `savefig(os.path.join(..., f"..."))` line and produces a correct-direction `savefig` edge (with literal variable resolution). The `fstring_path` event for this pattern appears to not be emitted at all (no duplicate wrong-direction entry in the CSV).
