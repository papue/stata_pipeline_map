# Cross-script global propagation — Stata replication findings

## Confirmed unresolved globals

| Child script | Global | Defined in | Expected resolved value |
|---|---|---|---|
| analysis/clean.do | `${ddir}` | master.do | `data/raw` |
| analysis/clean.do | `${pdir}` | master.do | `output` |
| analysis/regressions.do | `${pdir}` | master.do | `output` |
| pipeline/stage1_sub.do | `${stagedir}` | pipeline/stage1.do | `data/stage1` |

Note: `${stagedir}` itself depends on `${rootdir}` from master2.do, making the two-level
case a doubly-unresolved chain.

## Missing edges (because global unresolved)

| Script | Expected edge | Actual output |
|---|---|---|
| analysis/clean.do | reads `data/raw/survey.dta` | reads `{ddir}/survey.dta` (placeholder) |
| analysis/clean.do | writes `output/survey_clean.dta` | writes `{pdir}/survey_clean.dta` (placeholder) |
| analysis/regressions.do | reads `output/survey_clean.dta` | reads `{pdir}/survey_clean.dta` (placeholder) |
| analysis/regressions.do | writes `output/tables/baseline_regs.tex` | writes `{pdir}/tables/baseline_regs.tex` (placeholder) |
| pipeline/stage1_sub.do | reads `data/stage1/input.dta` | reads `{stagedir}/input.dta` (placeholder) |
| pipeline/stage1_sub.do | writes `data/stage1/output.dta` | writes `{stagedir}/output.dta` (placeholder) |

Because placeholder node IDs differ between scripts that write and scripts that read
(`analysis/clean.do` writes `{pdir}/survey_clean.dta` and `analysis/regressions.do` reads
the same placeholder key), the data-lineage link between clean.do and regressions.do is
still visible in the graph — but the nodes have wrong IDs and do not match the actual files
on disk (data/raw/survey.dta is not detected as consumed even though it exists as a file).

## Two-level failure

- Does stage1_sub.do fail to resolve `$stagedir`? **Yes** — reported as `{stagedir}/input.dta` and `{stagedir}/output.dta`
- Does it fail to resolve `$rootdir`? **Yes (indirectly)** — `$rootdir` is defined in master2.do; stage1.do builds `$stagedir = "${rootdir}/stage1"` but since `$rootdir` is unresolved at parse time of stage1.do, `$stagedir` is stored as `{rootdir}/stage1` rather than `data/stage1`, and that broken value propagates to stage1_sub.do as `{stagedir}`.

## Current behaviour in multi_extract.py

- Each script is parsed by an independent call to `parser(project_root, path, exclusions, normalization, parser_config)` at `multi_extract.py:193`.
- Inside `parse_do_file` (stata_extract.py line 334) a fresh `globals_map: dict[str, str] = {}` is initialised for every file — no globals survive across the call boundary.
- The `child_scripts` list returned by the parser is used to build script-call edges (multi_extract.py:211) but the globals accumulated during parsing are never passed to the child parsers.
- Consequence: any global defined in a parent script and used in a path expression inside a child script produces a `dynamic_path_partial_resolution` diagnostic and a placeholder node rather than a real file node.

## Validation diagnostics observed

Six `dynamic_path_partial_resolution` (info) diagnostics were produced:
- analysis/clean.do line 2 — pattern `{ddir}/survey.dta`
- analysis/clean.do line 4 — pattern `{pdir}/survey_clean.dta`
- analysis/regressions.do line 1 — pattern `{pdir}/survey_clean.dta`
- analysis/regressions.do line 3 — pattern `{pdir}/tables/baseline_regs.tex`
- pipeline/stage1_sub.do line 1 — pattern `{stagedir}/input.dta`
- pipeline/stage1_sub.do line 2 — pattern `{stagedir}/output.dta`

No diagnostics were produced for master.do or pipeline/stage1.do because those scripts
resolve their own globals correctly within their own parse context.
