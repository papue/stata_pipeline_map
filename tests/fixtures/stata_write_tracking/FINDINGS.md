# MO-05: Stata Write-Side Variable Tracking — Findings

## Summary

Tool: `data-pipeline-flow extract-edges` / `summary` / `validate`
Project root: `tests/fixtures/stata_write_tracking/`
Date: 2026-04-25

Total edges detected: **6** (3 read + 3 write)
Orphan scripts (no edges): **8**

---

## 1. Write Edges Detected (Working Correctly)

| Script | Pattern | Resolved Path | Edge in Output |
|--------|---------|---------------|----------------|
| `export_csv.do` | `local outpath + export delimited` | `../output/summary.csv` | YES |
| `export_excel.do` | `global tables + export excel using` | `../tables/table1.xlsx` | YES |
| `graph_save.do` | `local figdir + graph export` | `../figures/scatter.png` | YES |

Note: all three working cases produce deliverable-extension files (`.csv`, `.xlsx`, `.png`) which
pass the `suppress_internal_only_writes` filter because they are classified as `deliverable`.

---

## 2. Confirmed Missing Write Edges

### 2a. `.dta` saves suppressed by `suppress_internal_only_writes`

| Script | Pattern | Expected Edge | Tool Output | Root Cause |
|--------|---------|---------------|-------------|------------|
| `save_global.do` | `global outdir + save` | `output/results.dta` | **MISSING** — suppressed | `.dta` not in `deliverable_extensions`; no consumer → `intermediate` role → suppressed |
| `chained_macro.do` | chained globals (`root` + `out`) + `save` | `output/final.dta` | **MISSING** — suppressed | Same as above; path resolves to `../output/final.dta` (outside project root); role=`intermediate`, no consumer → suppressed |

Mechanism: `suppress_internal_only_writes=True` (default). The logic in `build_graph_from_do_files`
classifies `.dta` writes with `producer_exists=True` as `intermediate` (role). If no other script
consumes the artifact (i.e., `consumers.get(p, set()) <= {script}`), the edge is added to
`suppressed_internal_only` and dropped from the graph. An `unconsumed_output` diagnostic IS emitted,
but no edge is produced.

### 2b. Unresolved global produces wrong path with no partial-resolution marker

| Script | Pattern | Expected Edge | Tool Output | Root Cause |
|--------|---------|---------------|-------------|------------|
| `save_partial.do` | `${outdir}/${table_name}.dta` | placeholder `output/{table_name}.dta` | **MISSING** — suppressed | `${table_name}` is not in `globals_map`; `expand()` leaves it as literal `${table_name}`; `MACRO_TOKEN_RE` (backtick-only) does not detect it; resolution_status=`full` with a garbage path; then suppressed as `intermediate` |

Root cause detail: `expand()` only replaces known globals, leaving `${table_name}` literally in the
path string. `MACRO_TOKEN_RE = re.compile(r"`([^']+)'")` only matches backtick-quoted locals, not
`${...}` globals. So `_resolve_dynamic_path` returns status=`full` with a path containing a literal
dollar sign. The path `output/${table_name}.dta` is treated as a real path rather than a placeholder.
The `unconsumed_output` diagnostic is emitted but no edge is generated.

### 2c. Absolute path — write edge suppressed, only global-level warning emitted

| Script | Pattern | Expected Edge | Tool Output | Root Cause |
|--------|---------|---------------|-------------|------------|
| `save_absolute.do` | `global outpath "C:\..."` + `save` | absolute-path node + `absolute_path` diagnostic | **PARTIALLY** — diagnostic from global definition only; write edge suppressed | Absolute path in global fires `absolute_path_usage` warning at global-definition time. The global is normalized to `output` (last component); `save "${outpath}\results.dta"` resolves to `output/results.dta`. The write event also has `was_absolute=True`, but the edge is suppressed by `suppress_internal_only_writes` before the per-event absolute_path diagnostic is emitted. No edge appears in output. |

---

## 3. Missing Placeholder Nodes

| Script | Pattern | Expected Behavior | Tool Output |
|--------|---------|-------------------|-------------|
| `save_partial.do` | `${outdir}/${table_name}.dta` | `artifact_placeholder` node with `dynamic_path_partial_resolution` diagnostic | **NONE** — treated as full resolution; `${table_name}` left as literal string in path |

---

## 4. Commands Not Recognized by Parser (No Regex Defined)

| Script | Command | Expected Write Edge | Tool Output | WRITE_COMMANDS entry? |
|--------|---------|--------------------|--------------|-----------------------|
| `putexcel_save.do` | `putexcel set` | `tables/regression_results.xlsx` | **MISSING** — orphan | No |
| `outsheet_macro.do` | `outsheet using` | `output/data_out.csv` | **MISSING** — orphan | No |
| `log_macro.do` | `log using` | `logs/analysis.log` | **MISSING** — orphan | No |
| `esttab_macro.do` | `esttab ... using` | `tables/reg_table.tex` | **MISSING** — orphan | No |
| `outreg2_macro.do` | `outreg2 using` | `tables/outreg_table.doc` | **MISSING** — orphan | No |

Current `WRITE_COMMANDS` dictionary contains only: `save`, `export_delimited`, `export_excel`,
`graph_export`, `estimates_save`. None of `putexcel set`, `outsheet`, `log using`, `esttab ... using`,
or `outreg2 using` are present.

Note: `outsheet` is a read command (`insheet`) counterpart for writing CSVs and is sometimes confused
with `insheet`. The parser has `INSHEET_RE` in `READ_COMMANDS` but no corresponding `outsheet` write.
`log using` creates `.log` files; `.log` IS in `deliverable_extensions` but the command is entirely
absent from the parser.

---

## 5. Path Normalization Issue: `../` Escapes Project Root

Scripts in `scripts/` subdirectory that reference `"../output"` produce paths like `../output/results.dta`
as node IDs. These node IDs start with `../` and refer to locations outside the project root.

| Script | Resolved Node ID | Actual Project-Relative Path | Match? |
|--------|-----------------|------------------------------|--------|
| `save_global.do` | `../output/results.dta` | `output/results.dta` | NO |
| `export_csv.do` | `../output/summary.csv` | `output/summary.csv` | NO |
| `export_excel.do` | `../tables/table1.xlsx` | `tables/table1.xlsx` | NO |
| `graph_save.do` | `../figures/scatter.png` | `figures/scatter.png` | NO |
| `chained_macro.do` | `../output/final.dta` | `output/final.dta` | NO |

The three working write edges (`export_csv`, `export_excel`, `graph_save`) appear in the output CSV
with `../`-prefixed paths, meaning they point outside the project root instead of to the files that
actually exist at `output/`, `tables/`, `figures/`. This is a path normalization bug: scripts in
`scripts/` resolve relative paths relative to themselves, but `to_project_relative` does not
canonicalize away the `../` component.

---

## 6. Full CLI Output Reference

### `extract-edges` output (`/tmp/mo05_edges.csv`)

```
source,target,command,kind
data/clean.dta,scripts/export_csv.do,use,reference_input
data/results.dta,scripts/export_excel.do,use,reference_input
data/analysis.dta,scripts/save_global.do,use,reference_input
scripts/export_csv.do,../output/summary.csv,export_delimited,deliverable
scripts/export_excel.do,../tables/table1.xlsx,export_excel,deliverable
scripts/graph_save.do,../figures/scatter.png,graph_export,deliverable
```

### `summary` output (key diagnostics)

- `[warning] orphan_node`: 8 scripts have no edges (chained_macro, esttab_macro, log_macro,
  outreg2_macro, outsheet_macro, putexcel_save, save_absolute, save_partial)
- `[info] unconsumed_output`: 4 artifacts produced but not consumed
  - `../output/final.dta`, `output/results.dta`, `../output/results.dta`,
    `../output/${table_name}.dta`
- `[warning] absolute_path_usage`: fires for `save_absolute.do:1` (global definition)

---

## 7. Bug Classification

| # | Description | Category |
|---|-------------|----------|
| B1 | `.dta` files not in `deliverable_extensions` → all `save` writes to `.dta` are suppressed when unconsumed | Suppress logic / config gap |
| B2 | `suppress_internal_only_writes` suppresses write edges before per-event diagnostics (absolute_path, partial) are emitted | Logic ordering |
| B3 | `${...}` global references not detected by `MACRO_TOKEN_RE` (backtick-only) → unresolved globals produce full-resolution status with literal `$` in path | Parser gap |
| B4 | `putexcel set` command not in `WRITE_COMMANDS` | Missing regex |
| B5 | `outsheet using` command not in `WRITE_COMMANDS` | Missing regex |
| B6 | `log using` command not in `WRITE_COMMANDS` | Missing regex |
| B7 | `esttab ... using` command not in `WRITE_COMMANDS` | Missing regex |
| B8 | `outreg2 using` command not in `WRITE_COMMANDS` | Missing regex |
| B9 | `../` paths not canonicalized → write edge targets point outside project root | Normalization gap |
