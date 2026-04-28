# FD-05 Findings — Stata macro-constructed paths: wrong/missing edges

## Tool run

```
data-pipeline-flow extract-edges \
  --project-root tests/fixtures/fstring_direction_stata \
  --output /tmp/fd05_edges.csv
```

## Actual edges

```
source,target,command,kind
data/estimates.dta,analysis/export_results.do,use,reference_input
data/input.dta,analysis/generate_tables.do,use,reference_input
data/estimates.dta,analysis/reg_tables.do,use,reference_input
analysis/generate_tables.do,results/tables/summary_stats.dta,save,deliverable
analysis/reg_tables.do,results/tables/baseline_regs.tex,esttab,deliverable
```

## Expected edges (writes only)

| Script | Expected target | Status |
|--------|----------------|--------|
| `generate_tables.do` | `results/tables/summary_stats.dta` | CORRECT — macro expansion resolved both locals |
| `export_results.do`  | `results/welfare_table.xlsx`        | **MISSING** — write edge absent |
| `reg_tables.do`      | `results/tables/baseline_regs.tex`  | CORRECT — esttab macro expansion resolved |

## Root cause

**Bug location:** `src/data_pipeline_flow/parser/stata_extract.py`, line 27.

```python
EXPORT_EXCEL_RE = re.compile(r'\bexport\s+excel\s+using\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
```

`EXPORT_EXCEL_RE` requires the literal keyword `using` between `export excel` and the
filename.  In valid Stata syntax `using` is optional — the path may follow directly:

```stata
export excel "${outdir}/`metric'_table.xlsx", replace firstrow(variables)
```

Because `using` is absent, the regex never matches, and no write edge is emitted for
`export_results.do`.

The mixed global/local macro substitution (`${outdir}` + backtick local) is a secondary
concern: even if the regex matched the raw string `"${outdir}/`metric'_table.xlsx"`,
`_resolve_dynamic_path` would need to handle the combined form.  However the primary
failure is the missing `using` keyword — the line is never captured at all.

## Summary of confirmed bugs

1. **EXPORT_EXCEL_RE missing `using`-optional branch** — regex requires `using` but Stata
   allows the filename directly after `export excel`.  Fix: make `(?:using\s+)?` optional,
   matching `export excel <path>` and `export excel using <path>`.
