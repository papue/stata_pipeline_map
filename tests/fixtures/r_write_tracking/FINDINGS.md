# MO-03: R Write-Side Variable Tracking — Findings

Fixture project: `tests/fixtures/r_write_tracking/`
Tool run: `data-pipeline-flow extract-edges / summary / validate`
Date: 2026-04-25

---

## CLI Output (extract-edges)

```
source,target,command,kind
analysis/export_results.r,output/results.csv,write_csv,deliverable
analysis/plot_save.r,analysis/plots/distribution.png,ggsave_kw,deliverable
analysis/save_model.r,models/fit.rds,saveRDS_kw,deliverable
analysis/write_readr.r,output/data.csv,write_csv_readr,deliverable
save_absolute.r,c:/project/output/summary.csv,write_csv,deliverable
```

Summary: 5 edges detected, 5 scripts produce no write edges (orphan nodes).

---

## Write Edges — Confirmed Working

| Script | Pattern | Command matched | Edge detected |
|--------|---------|-----------------|---------------|
| `analysis/export_results.R` | `write.csv(df, out_path)` where `out_path` is `file.path(script_dir, "..", "output", "results.csv")` | `write_csv` | `output/results.csv` ✓ |
| `analysis/plot_save.R` | `ggsave(filename = plot_path)` where `plot_path` is `file.path(script_dir, "plots", "distribution.png")` | `ggsave_kw` | `analysis/plots/distribution.png` ✓ |
| `analysis/save_model.R` | `saveRDS(model, file = model_path)` where `model_path` is `file.path(script_dir, "..", "models", "fit.rds")` | `saveRDS_kw` | `models/fit.rds` ✓ |
| `analysis/write_readr.R` | `write_csv(df, out_path)` where `out_path` is `file.path(script_dir, "..", "output", "data.csv")` | `write_csv_readr` | `output/data.csv` ✓ |
| `save_absolute.R` | `write.csv(df, out_path)` where `out_path` is `file.path(output_dir, "summary.csv")`, `output_dir <- "C:/project/output"` | `write_csv` | `c:/project/output/summary.csv` ✓ (with `absolute_path_usage` diagnostic) |

**Note on `absolute_path_usage` warnings:** Scripts that use `dirname(sys.frame(1)$ofile)` resolve `script_dir` to the absolute filesystem path (e.g. `D:/Sciebo New/.../analysis`). When this is embedded into `file.path(...)`, the resulting path is absolute. The parser detects this as `was_absolute=True` and emits an `absolute_path_usage` warning for each such script — even when the edge target resolves correctly to a project-relative path. This is expected but potentially noisy.

---

## Confirmed Missing Write Edges

| Script | Pattern | Expected edge | Tool output | Root cause |
|--------|---------|---------------|-------------|------------|
| `analysis/write_xlsx.R` | `writexl::write_xlsx(df, path = xlsx_path)` | `output/report.xlsx` | No edge (orphan) | `write_xlsx` pattern matches only the **second positional arg** (`[^,]+,\s*"path"`). The `path=` keyword argument form is not handled. Even with the variable fully substituted, `path = "..."` does not match `[^,]+,\s*"..."`. |
| `analysis/write_parquet.R` | `write_parquet(df, sink = sink_path)` | `output/results.parquet` | No edge (orphan) | `write_parquet` pattern matches only the **second positional arg**. The `sink=` keyword argument used by arrow's `write_parquet()` is not handled. |
| `analysis/write_png_device.R` | `png(filename = png_path)` | `analysis/plots/figure.png` | No edge (orphan) | The `png` pattern (`\bpng\s*\(\s*"path"`) matches only a **first positional** argument. The `filename=` keyword argument is not handled. |
| `analysis/write_cat.R` | `cat("some output\n", file = log_path)` | `output/log.txt` | No edge (orphan) | **`cat()` has no pattern at all** in `_WRITES_KEYWORD` or `_WRITES_DATA_THEN_PATH`. The `file=` argument form used with `cat()`, `message()`, etc. is entirely unrecognised. |

---

## Missing Placeholder Nodes (Variable / Loop Patterns)

| Script | Pattern | Expected placeholder | Tool output | Root cause |
|--------|---------|----------------------|-------------|------------|
| `analysis/plot_loop.R` | `ggsave(filename = file.path(script_dir, "plots", paste0("plot_", treatment, ".png")))` | `analysis/plots/plot_{treatment}.png` or similar | No edge (orphan) | `paste0()` contains the loop variable `treatment` which is not in `vars_map`. `_resolve_paste0` returns `None`, so the whole `file.path()` call is unresolvable. No placeholder node is emitted — the write call is silently dropped. |

---

## Additional Patterns Tested

| Script | Command | Keyword / form | Detected? |
|--------|---------|----------------|-----------|
| `write_xlsx.R` | `writexl::write_xlsx` | `path=` keyword | No |
| `write_parquet.R` | `write_parquet` | `sink=` keyword | No |
| `write_png_device.R` | `png` | `filename=` keyword | No |
| `write_cat.R` | `cat` | `file=` keyword | No (no pattern) |
| `plot_loop.R` | `ggsave` | dynamic `paste0` loop var | No (unresolvable) |

### Patterns that *would* have matched but for keyword-arg form

The following were confirmed by manual regex test:
- `write_xlsx(df, "/resolved/path.xlsx")` — **matches** `write_xlsx` pattern (positional works)
- `write_parquet(df, "/resolved/path.parquet")` — **matches** `write_parquet` pattern (positional works)
- `png("/resolved/path.png")` — **matches** `png` pattern (positional works)

This confirms the bug is specifically the **keyword-argument form** not being handled, not the function name recognition itself.

---

## Summary of Gaps

1. **Keyword-arg `path=` for `write_xlsx`** — `writexl::write_xlsx(df, path = ...)` is the idiomatic form recommended in writexl docs; the second-positional-only pattern misses it.
2. **Keyword-arg `sink=` for `write_parquet`** — arrow's `write_parquet(df, sink = ...)` uses `sink=` not a positional path; not handled.
3. **Keyword-arg `filename=` for `png()`** — `png(filename = ...)` is extremely common (RStudio auto-complete inserts it); the positional-only pattern misses it. Same issue likely applies to `jpeg()`, `tiff()`, `svg()`, `pdf()`.
4. **`cat()` with `file=` not tracked at all** — `cat(..., file = path)` / `message(..., file = path)` produce text output files; no pattern exists.
5. **Loop variable in `paste0`** — When a dynamic loop variable appears in a path construction (`paste0("prefix_", var, ".ext")`), the path is silently dropped with no placeholder node. A placeholder like `analysis/plots/plot_{?}.png` would be more informative.
6. **`absolute_path_usage` false positives** — Scripts using `dirname(sys.frame(1)$ofile)` trigger `absolute_path_usage` warnings even when the final edge resolves correctly to a project-relative path. The warning is technically correct but may be misleading in practice.
