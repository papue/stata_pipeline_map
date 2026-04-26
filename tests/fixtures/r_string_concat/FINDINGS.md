# MO-15 Findings: R String Concatenation as Path Join

## Summary

Eight fixture scripts tested. After MO-16 fixes, **7 of 8** produce correct edges.
The remaining case (`concat_loop.R`) uses a loop variable that is unresolvable at
static-analysis time — this is expected behaviour.

---

## Missing Edges (before fix)

| Script | Pattern | Expected edge | Actual (before fix) | Root cause |
|--------|---------|---------------|---------------------|------------|
| `analysis/concat_sep.R` | `paste0(base, "/", name, ".csv")` | `data/final.csv` | `data/final/.csv` | `_resolve_paste0` called `_resolve_path_args` which joined args with `/` instead of concatenating directly |
| `analysis/paste_sep.R` | `paste(base, "file.csv", sep="/")` | `data/file.csv` | (no edge) | No regex or resolver for `paste(…, sep=…)` |
| `analysis/nested_paste0.R` | `paste0(paste0(base, "/sub"), "/file.csv")` | `data/sub/file.csv` | `data/sub` | `[^)]+` regex matched first `)`, capturing inner args only; vars_map overwrite bug in iteration loop |
| `analysis/concat_loop.R` | `paste0(file.path(script_dir, "plots"), "/plot_", treatment, ".png")` | partial `plots/plot_{treatment}.png` | (no edge) | Loop variable `treatment` is unresolvable — acceptable |

---

## Working Patterns (before fix)

| Script | Pattern | Edge produced |
|--------|---------|---------------|
| `analysis/concat_read.R` | `path <- paste0(base, "/results.csv")` then `read.csv(path)` | `data/results.csv` → script |
| `analysis/sprintf_path.R` | `sprintf("%s/results_%s.csv", base_dir, suffix)` | `data/results_final.csv` → script |
| `analysis/concat_write.R` | `file.path(script_dir, "..", "output")` + `paste0(base, "/summary.csv")` | script → `output/summary.csv` |
| `concat_absolute.R` | `paste0(output_path, "/merit_order.png")` | script → `c:/project/output/merit_order.png` |

---

## Additional Patterns Tested

| Script | Pattern | Status after fix |
|--------|---------|-----------------|
| `analysis/paste_sep.R` | `paste(base, "file.csv", sep="/")` | Fixed — new `_resolve_paste_sep_args` + `_PASTE_SEP_RE` |
| `analysis/nested_paste0.R` | `paste0(paste0(a, b), c)` | Fixed — balanced-paren extraction + iteration guard |
| `analysis/concat_sep.R` | `paste0(a, "/", b, ".csv")` | Fixed — use concat (no sep) instead of path-join |

---

## Fixes Applied (MO-16)

1. **`paste0` joins by concatenation, not `/`**: `_resolve_paste0` now calls
   `_resolve_paste0_args` (direct concat) instead of `_resolve_path_args` (joins with `/`).

2. **Balanced-paren extraction**: New `_extract_balanced_args` function correctly
   handles nested calls (`paste0(paste0(…), …)`) by tracking parenthesis depth.

3. **`paste(a, b, sep="/")` support**: New `_resolve_paste_sep_args` function and
   `_resolve_paste_sep` helper added. Integrated into both `_apply_balanced_substitutions`
   and the `vars_map` assignment pass.

4. **`_apply_balanced_substitutions` replaces `_preprocess_helpers`**: Single unified
   function handles `paste0`, `paste(sep=)`, `file.path`, `here`/`here::here`, and
   `sprintf` with iterative inner-first resolution.

5. **`here::here` namespace fix**: Restored `_HERE_RE`-based substitution inside
   `_apply_balanced_substitutions` to avoid matching bare `here` inside `here::here`.

6. **vars_map overwrite guard**: In the second-pass assignment loop, the LHS variable
   name is excluded from var-expansion to prevent `path <- paste0(…)` becoming
   `"value" <- paste0(…)` on iteration 2, which triggered the fallback and overwrote
   the correct value.

---

## Final Edge List (after fix)

```
data/results.csv     → analysis/concat_read.r     (read_csv)
data/final.csv       → analysis/concat_sep.r      (read_csv)
data/sub/file.csv    → analysis/nested_paste0.r   (read_csv)
data/file.csv        → analysis/paste_sep.r       (read_csv)
data/results_final.csv → analysis/sprintf_path.r  (read_csv)
analysis/concat_write.r → output/summary.csv      (write_csv)
concat_absolute.r    → c:/project/output/merit_order.png (ggsave)
```
