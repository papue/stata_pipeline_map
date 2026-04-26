# MO-12 Findings: `../`-Prefixed Path Normalization

## Fixture: `tests/fixtures/stata_abs_normalization/`

This fixture was created to reproduce a node ID mismatch where two different node IDs
referred to the same physical file.

## Node ID Mismatch (pre-fix)

| Script | Command | Raw path in .do file | Produced node ID | Expected node ID |
|---|---|---|---|---|
| `scripts/extract.do` | `save` | `C:\project_external\data\all_results.dta` | `data/all_results.dta` | `data/all_results.dta` |
| `scripts/analyze.do` | `use` | `"../data/all_results.dta"` | `../data/all_results.dta` | `data/all_results.dta` |
| `scripts/analyze.do` | `save` | `"../output/summary.dta"` | `../output/summary.dta` | `output/summary.dta` |

`data/all_results.dta` and `../data/all_results.dta` appeared as **two separate nodes**,
so the `extract.do → all_results.dta → analyze.do` pipeline chain was broken.

## Root Cause

Scripts in a `scripts/` subdirectory that write relative paths like `"../data/file.dta"`
produced node IDs that retained the leading `../`.

The path `"../data/all_results.dta"` written in `scripts/analyze.do` should resolve as:

```
scripts/../data/all_results.dta  →  data/all_results.dta  (project-root-relative)
```

But instead it was passed as-is to `to_project_relative`, which left it as
`../data/all_results.dta` because it is neither absolute nor rooted under the
project root directory.

## Fix (MO-12)

`_resolve_script_relative(do_file, expanded)` was added to
`src/data_pipeline_flow/parser/stata_extract.py`.

When a path contains `..` and is not absolute, it resolves the path against the
script's own directory (not the project root) before passing it to
`to_project_relative`. This mirrors the approach used by `python_extract.py` for
`__file__`-relative paths.

Call sites covered:
- `do` child-script references (line ~362)
- READ_COMMANDS (`use`, `import`, `append`, `merge`, `cross`) loop (line ~380)
- WRITE_COMMANDS (`save`, `export_delimited`, etc.) loop (line ~403)

## Verified Output (post-fix)

```
source,target,command,kind
data/all_results.dta,scripts/analyze.do,use,intermediate
data/analysis.dta,scripts/chained_global.do,use,reference_input
raw/source.dta,scripts/extract.do,use,reference_input
scripts/analyze.do,output/summary.dta,save,deliverable
scripts/chained_global.do,data/output.csv,export_delimited,deliverable
scripts/extract.do,data/all_results.dta,save,deliverable
```

`data/all_results.dta` appears exactly once. The pipeline chain is intact:

```
raw/source.dta → scripts/extract.do → data/all_results.dta → scripts/analyze.do → output/summary.dta
```

## Scope Note

This fix was applied to the **Stata parser only** (MO-12). Python and R extractors
have a similar `../` normalization gap but are out of scope for this task.
