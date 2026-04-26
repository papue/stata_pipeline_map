# FINDINGS -- R kwarg/path-wrapper patterns (Task MO-21)

Fixture project: `tests/fixtures/r_kwarg_pathlib/`
Tool run: `extract-edges --project-root tests/fixtures/r_kwarg_pathlib`
Output CSV: `viewer_output/parser_edges.csv`

---

## 1. Results table

| Script | Pattern | Expected edge (target) | Detected? |
|--------|---------|------------------------|-----------|
| `norm_path.R` | `normalizePath(raw_path)` wrapper, then `ggsave(clean_path)` | `analysis/plots/output.png` | NO |
| `fs_path.R` | `fs::path(script_dir, "plots", "fs_chart.png")` then `ggsave(out_path)` | `analysis/plots/fs_chart.png` | NO |
| `kwarg_helper.R` | `plot_results(df, filename = file.path(..., "results_a.png"))` | `analysis/plots/results_a.png` | NO |
| `kwarg_helper.R` | `plot_results(df, filename = file.path(..., "results_b.png"))` | `analysis/plots/results_b.png` | NO |
| `kwarg_helper.R` | `plot_results(df, filename = file.path(..., "results_c.png"))` | `analysis/plots/results_c.png` | NO |
| `ggsave_kwarg.R` | `out_file <- file.path(...)` then `ggsave(filename = out_file, ...)` | `analysis/plots/final_plot.png` | YES |
| `extra_patterns.R` | `writeLines(c("line1", "line2"), con = out_file)` | `analysis/output/report.txt` | NO (false positive instead -- see section 4) |
| `extra_patterns.R` | `cat("text", file = file.path(script_dir, "plots", "log.txt"))` | `analysis/plots/log.txt` | YES |
| `extra_patterns.R` | `svg(filename = file.path(script_dir, "plots", "device.svg"))` | `analysis/plots/device.svg` | YES |
| `extra_patterns.R` | `out <- here("output", "chart.png")` then `ggsave(out)` | `output/chart.png` | NO |

---

## 2. Patterns already handled

The following patterns produce correct edges:

- **`ggsave(filename = <variable>)` when the variable was assigned via `file.path(script_dir, ...)`**
  The second-pass assignment handler (lines ~795-801 in r_extract.py) stores the
  resolved path in `vars_map`; the main-loop variable expansion then substitutes it
  inline before the `ggsave_kw` regex fires.
  Actual edge detected: `analysis/ggsave_kwarg.r -> analysis/plots/final_plot.png`
  (command: `ggsave_kw`)

- **`cat("text", file = file.path(...))` with an inline `file.path(...)` in the keyword arg**
  `_preprocess_helpers` resolves `file.path(...)` to a quoted string before the
  `cat_file` pattern fires.
  Actual edge detected: `analysis/extra_patterns.r -> analysis/plots/log.txt`
  (command: `cat_file`)

- **`svg(filename = file.path(...))` with an inline `file.path(...)` in the keyword arg**
  Same inline substitution mechanism as `cat` above.
  Actual edge detected: `analysis/extra_patterns.r -> analysis/plots/device.svg`
  (command: `svg_kw`)

---

## 3. Confirmed missing patterns

### 3a. `normalizePath()` as a path-building wrapper

Script: `norm_path.R`

```r
raw_path <- file.path(script_dir, "plots", "output.png")
clean_path <- normalizePath(raw_path, mustWork = FALSE)
ggsave(clean_path)
```

Root cause: `normalizePath(...)` is not recognized as a path-propagating function.
The second-pass assignment handler has explicit cases for `file.path`, `paste0`,
`paste(sep=)`, `sprintf`, and `here`/`here::here`, but not for `normalizePath`.
`raw_path` IS stored in `vars_map` correctly (via the `file.path` handler), but
`clean_path <- normalizePath(raw_path, ...)` has no handler, so `clean_path` stays
out of `vars_map`. The final `ggsave(clean_path)` then has nothing to expand.

Fix required: Add a second-pass handler for `var <- normalizePath(other_var, ...)`
that looks up `other_var` in `vars_map` and propagates its value to `var`.

---

### 3b. `fs::path()` as a path-building function

Script: `fs_path.R`

```r
out_path <- fs::path(script_dir, "plots", "fs_chart.png")
ggsave(out_path)
```

Root cause: `fs::path(...)` is not in the set of recognized path helpers.
`_apply_balanced_substitutions` handles `file.path`, `paste0`, `paste(sep=)`,
`here`/`here::here`, and `sprintf`, but not `fs::path`. The namespaced `fs::` prefix
means the call also cannot match a bare `path(` regex. As a result `out_path` is never
stored in `vars_map` and `ggsave(out_path)` produces no match.

Fix required: Add `fs::path(...)` to `_apply_balanced_substitutions` and to the
second-pass `var <- fs::path(...)` assignment handler, treating it identically to
`file.path` (slash-joined components).

---

### 3c. Call-site keyword arguments on user-defined functions

Script: `kwarg_helper.R`

```r
plot_results(df, filename = file.path(script_dir, "plots", "results_a.png"))
```

Root cause: The extractor only recognizes `filename=`, `file=`, and `con=` keyword
arguments on a fixed allowlist of known write functions (`ggsave`, `saveRDS`, `save`,
`pdf`, `png`, `svg`, etc.). User-defined functions like `plot_results` are not on this
list. Even though the call site provides a fully resolvable `file.path(...)` literal
for `filename=`, there is no mechanism to trace write side effects through user-defined
function calls.

Fix required (complex): Add a heuristic that recognizes any function call containing
`filename = <resolvable-path>` or `file = <resolvable-path>` as a probable write,
regardless of function name, and emits an edge with an `inferred` command label.

---

### 3d. `here("...")` assigned to variable, then passed to a write function

Script: `extra_patterns.R`

```r
out <- here("output", "chart.png")
ggsave(out)
```

Root cause: `_apply_balanced_substitutions` handles `here::here(...)` inline (it
substitutes the resolved path directly in the line being processed), but the
second-pass variable assignment handler only has explicit cases for `file.path`,
`paste0`, `paste(sep=)`, and `sprintf`. There is no case for `var <- here(...)` or
`var <- here::here(...)`. So `out` is never stored in `vars_map`, and `ggsave(out)`
produces no match.

Note: `_HERE_RE` matches both `here(...)` and `here::here(...)` via the pattern
`r'\bhere(?:::here)?\s*\(([^)]+)\)'`. Inline use would work (e.g. if the code were
`ggsave(here("output", "chart.png"))` on a single line), but the two-step
assign-then-use pattern is not supported.

Fix required: Add a second-pass handler for `var <- here(...)` and
`var <- here::here(...)`, analogous to the existing `var <- file.path(...)` handler
at lines ~795-801 in r_extract.py.

---

## 4. Additional patterns from `extra_patterns.R`

### `writeLines(c("line1", "line2"), con = out_file)` -- variable in `con=`

Expected edge: `analysis/output/report.txt`
(since `out_file <- file.path(script_dir, "..", "output", "report.txt")` is fully
resolvable and IS stored in `vars_map` by the second-pass `file.path` handler)

Detected: (nothing for the intended target)

False positive detected: The positional-form `writeLines` pattern fires and captures
`"line2"` as a spurious write target. The regex
`\bwriteLines\s*\([^,]+,\s*"([^"]+)"` matches `writeLines(c("line1", "line2"`
because `[^,]+` stops at the first comma -- which is the comma INSIDE `c("line1", ...)`
-- leaving `"line2"` as the apparent second positional argument. The tool emits the
artifact node `line2` (orphaned in the graph).

The keyword-form `writeLines_kw` pattern (`con = "..."`) never gets tried because the
positional match fires first (`_WRITES_DATA_THEN_PATH` is checked before
`_WRITES_KEYWORD` in `all_write_patterns`) and sets `matched_write = True`.

Root causes (two bugs):
1. `[^,]+` in the positional `writeLines` regex ignores nested parentheses, causing
   a false positive match on the inner `c(...)` argument.
2. The keyword-form `con = out_file` (variable, not literal) would need variable
   expansion to fire -- but the positional match preempts it.

### `cat("text", file = file.path(script_dir, "plots", "log.txt"))` -- inline `file.path`

Detected: YES -- `analysis/plots/log.txt` via `cat_file`.
`_preprocess_helpers` resolves `file.path(...)` inline before `cat_file` fires.
Works correctly.

### `svg(filename = file.path(script_dir, "plots", "device.svg"))` -- inline `file.path`

Detected: YES -- `analysis/plots/device.svg` via `svg_kw`.
Same mechanism as `cat` above. Works correctly.

### `out <- here("output", "chart.png")` then `ggsave(out)`

Detected: NO -- see section 3d above. `here(...)` assignment is not tracked in
the second pass, so `out` is unknown at the `ggsave` call.

---

## 5. Summary of bugs

| # | Pattern | Root cause |
|---|---------|------------|
| B1 | `normalizePath(var)` wrapper | Not in second-pass assignment handlers |
| B2 | `fs::path(...)` path builder | Not in `_apply_balanced_substitutions` or second-pass handlers |
| B3 | User-defined function call-site kwargs (`filename=`, `file=`) | No mechanism to inspect user-defined function arguments |
| B4 | `here(...)` / `here::here(...)` assigned to variable then used | Not in second-pass assignment handlers; only inline substitution is supported |
| B5 | `writeLines(c(...), con=var)` false positive | Positional `[^,]+` ignores nested parens; matches inner `c()` element as file path |
