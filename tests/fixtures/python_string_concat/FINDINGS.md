# MO-13 Findings: Python String Concatenation Path Building

## Missing edges before fix (MO-13 replication)

| Script | Pattern | Expected edge | Pre-fix result |
|--------|---------|---------------|---------------|
| `merit_order_plot.py` | `abs_var + r"\file.ext"` | `merit_order_plot.py → merit_order.png` | NOT detected |
| `analysis/concat_vars.py` | `var_path + var_suffix` (both vars) | `output/results_final.csv → concat_vars.py` | NOT detected |
| `analysis/chained_plus.py` | `a + b + c` (three-var chain) | `data/sub/file.csv → chained_plus.py` | NOT detected |

Scripts that worked BEFORE the fix:
- `analysis/concat_relative.py`: `os.path.join(...) + "/" + "file.csv"` — already handled by `_VAR_OSPATH_JOIN_PLUS_RE`
- `analysis/osep_concat.py`: `os.path.join(...) + os.sep` then `f"{var}file"` — `os.sep` substituted to `"/"` in pre-pass
- `analysis/percent_fmt.py`: `"%s/file.csv" % base` — already handled by `_VAR_PERCENT_FORMAT_RE`
- `analysis/format_method.py`: `"{}/file.csv".format(base)` — already handled by `_VAR_FORMAT_METHOD_RE`

## Root causes found

### Bug 1: `/suffix` strings incorrectly added to `abs_vars`
In sub-pass 1a, `suffix = "/results_final.csv"` was added to `abs_vars` because `_is_absolute_like("/results_final.csv")` returned `True` (starts with `/`). Once in `abs_vars`, its value was skipped during concat resolution, so `prefix + suffix` yielded only `prefix`.

**Fix**: Added `_is_absolute_base()` helper that requires Unix absolute paths to have more than one path segment (i.e., `/home/user` yes, `/file.csv` no). Sub-pass 1a now uses `_is_absolute_base()` instead of `_is_absolute_like()`.

### Bug 2: No chained `+` concat resolver
The old `_VAR_CONCAT_RE` only handled `var + "literal"` (one var and one quoted literal). Patterns like `var + var` or `a + b + c` were not matched.

**Fix**: Added `_VAR_CONCAT_CHAIN_RE` regex and `_resolve_concat_chain()` helper that tokenizes any `+`-chain into vars and quoted literals, resolves each token from `vars_map`, and concatenates the results. Abs-vars in the chain are skipped (only the relative suffix parts are retained) with `contained_absolute=True` so a `force_abs` edge can still be emitted.

## Working patterns after fix

| Pattern | Example | Status |
|---------|---------|--------|
| `var + "literal"` | `base + "input.csv"` | ✓ Working |
| `var + var` | `prefix + suffix` | ✓ Fixed |
| `a + b + c` (chained) | `a + b + c` | ✓ Fixed |
| `abs_var + "suffix"` | `output_path + r"\file.png"` | Partial: emits node with abs flag |
| `"%s/f" % var` | `"%s/input.csv" % base` | ✓ Already worked |
| `"{}/f".format(var)` | `"{}/input.csv".format(base)` | ✓ Already worked |
| `os.path.join(...) + "/"` | `os.path.join(d, "sub") + "/"` | ✓ Already worked |
| `f"{var}file.csv"` | `f"{data_path}all_results.parquet"` | ✓ Already worked |

## Additional patterns tested (brainstorm)

- **`var + var` (both vars)**: now fixed by `_VAR_CONCAT_CHAIN_RE`
- **Chained `a + b + c`**: now fixed
- **`abs_var + r"\file.ext"`** (Windows raw string suffix): edge emitted with `was_absolute=True`; the resolved file node is `/file.ext` (stripped of Windows path)
- **`"/suffix"` as variable**: correctly excluded from `abs_vars` after the `_is_absolute_base` fix

## Final edge list (post-fix)

```
data/sub/file.csv          → analysis/chained_plus.py    (read_csv)
data/input.csv             → analysis/concat_relative.py (read_csv)
output/results_final.csv   → analysis/concat_vars.py     (read_csv)
data/input.csv             → analysis/format_method.py   (read_csv)
results/all_results.parquet           → analysis/osep_concat.py (read_parquet)
results/all_results_multit.parquet    → analysis/osep_concat.py (read_parquet)
data/input.csv             → analysis/percent_fmt.py     (read_csv)
merit_order_plot.py        → /merit_order.png            (savefig, abs-flagged)
```
