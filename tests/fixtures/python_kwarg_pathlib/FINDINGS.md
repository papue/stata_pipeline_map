# Python kwarg path and pathlib findings

**Note:** All fixes were already implemented by the MO-19/MO-20 agent before the session limit was hit.
FINDINGS.md reconstructed from the actual CLI output.

## Final edges detected (all working)

| Source | Target | Command |
|--------|--------|---------|
| `analysis/kwarg_helper.py` | `analysis/plots/benchmark.png` | `kwarg_write` |
| `analysis/kwarg_helper.py` | `analysis/plots/price_avg.png` | `kwarg_write` |
| `analysis/kwarg_helper.py` | `analysis/plots/quantity_avg.png` | `kwarg_write` |
| `analysis/kwarg_via_var.py` | `analysis/plots/fig_a.png` | `kwarg_write` |
| `analysis/kwarg_via_var.py` | `analysis/plots/fig_b.png` | `kwarg_write` |
| `analysis/output_kwarg.py` | `output/final.csv` | `kwarg_write` |
| `analysis/pathlib_direct.py` | `analysis/plots/direct.png` | `savefig` |
| `analysis/pathlib_div.py` | `output/results.csv` | `to_csv` |
| `analysis/pathlib_wrap.py` | `analysis/plots/chart.png` | `kwarg_write` |

## Fixes applied (in python_extract.py)
- Fix A: `pathlib.Path(var)` transparent unwrapping; Path `/` operator as path join
- Fix B: kwarg heuristic — keyword args named `filename`, `path`, `output`, `output_path`,
  `save_path`, `filepath`, `file`, `fname` emit write edges when the value is resolvable

## Confirmed missing before fix (all now resolved)
- `pathlib_wrap.py`: `Path(filename)` → `savefig(path)` — was not detected
- `kwarg_helper.py`: `filename=join(...)` passed to user-defined helper — was not detected
- `kwarg_via_var.py`: `output_path=var` passed to user-defined helper — was not detected
