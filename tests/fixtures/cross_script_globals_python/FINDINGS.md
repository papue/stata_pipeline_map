# CSG-05 Findings — Python Cross-Script Global Propagation

## Tool invocation

```
data-pipeline-flow extract-edges \
  --project-root tests/fixtures/cross_script_globals_python \
  --output /tmp/csg05_edges.csv
```

## Actual edges emitted

```
source,target,command,kind
config.py,analysis/evaluate.py,import,script_call
config.py,analysis/fit_model.py,import,script_call
*/evaluation.csv,analysis/evaluate.py,fstring_path,reference_input
*/predictions.parquet,analysis/evaluate.py,fstring_path,reference_input
*/features.parquet,analysis/fit_model.py,fstring_path,reference_input
*/predictions.parquet,analysis/fit_model.py,fstring_path,reference_input
```

## Expected edges (if constants were resolved)

| Script | Direction | Path |
|---|---|---|
| analysis/fit_model.py | reads | data/processed/features.parquet |
| analysis/fit_model.py | writes | output/results/predictions.parquet |
| analysis/evaluate.py | reads | output/results/predictions.parquet |
| analysis/evaluate.py | writes | output/results/evaluation.csv |

---

## Bugs confirmed

### Bug 1 — Imported constants not propagated into f-string paths (FIXABLE)

**Pattern:** `from config import DATA_DIR, OUTPUT_DIR` followed by
`f"{DATA_DIR}/features.parquet"`.

The parser detects the `from config import` and creates a `script_call` edge from
`config.py` to the calling script. However, it does NOT load the string values of
`DATA_DIR` and `OUTPUT_DIR` from `config.py` and substitute them when resolving f-string
paths in the calling script.

Result: paths are emitted as `*/features.parquet` (glob placeholder) instead of the
fully resolved `data/processed/features.parquet`.

**Why it is fixable:** The imported names map directly to simple string literals in
`config.py`. A two-pass approach — parse the imported module first, build a symbol table
of `NAME = "literal"` assignments, then inject those into the calling script's variable
context — would resolve this class of paths. This is analogous to the Stata
`global`-propagation fix (CSG-01/02) and the R `source()` propagation fix (CSG-03/04).

**Scope of fix:** Only covers `from <module> import <NAME>` where `<module>` is a
project-local `.py` file and the imported names resolve to string literals or simple
string concatenations. Dynamic values (env vars, function returns, runtime args) remain
out of scope.

### Bug 2 — Write calls emitted with wrong direction (separate, pre-existing issue)

`to_parquet(...)` and `to_csv(...)` calls are reported as `reference_input` (reads)
rather than `reference_output` (writes). This is a pre-existing parser limitation and is
out of scope for this task.

---

## Pattern: subprocess.run with CLI args — OUT OF SCOPE

`run_pipeline.py` passes `DATA_ROOT` and `OUTPUT_ROOT` as command-line arguments to
called scripts:

```python
subprocess.run(["python", "analysis/stage1.py", "--data", DATA_ROOT, "--out", OUTPUT_ROOT])
```

The called scripts (`stage1.py`, `stage2.py`) would receive these as `sys.argv` values
and parse them with `argparse` or similar. Static analysis cannot determine how those
args are consumed inside the called scripts without executing them.

**Classification: not fixable with current architecture.** The subprocess call itself is
not even a dependency edge in any meaningful sense — it passes data at runtime, not via
shared files. No fix is warranted. Document the pattern and move on.

`run_pipeline.py` correctly appears as an orphan node in the diagnostic output (no
incoming or outgoing data-file edges).

---

## Summary table

| Pattern | Fixable? | Notes |
|---|---|---|
| `from config import X` → f-string path | Yes | Two-pass symbol table per imported module |
| `import config; config.X` in expression | Partial | Would need attribute-access tracking |
| `subprocess.run([..., VAR, ...])` as arg | No | Runtime, not static |
| `to_parquet` / `to_csv` direction | Pre-existing bug | Out of scope here |
