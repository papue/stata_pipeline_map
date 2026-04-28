# FD-03 Findings — R fstring-path direction / resolution bugs

Fixture: `tests/fixtures/fstring_direction_r/`
Tool run: `data-pipeline-flow extract-edges`

---

## Summary of actual edges produced

| source | target | direction | correct? |
|--------|--------|-----------|----------|
| analysis/plot_results.r | plots/baseline.png | script → file (write) | YES |
| analysis/export_pdf.r | results/scenario_a_alpha%.2f.pdf | script → file (write) | PARTIAL — path wrong |
| analysis/heatmap.r | (none) | — | MISSING |

---

## Bug 1 — `glue()` paths are not resolved (heatmap.R — MISSING edge)

`fig_path <- glue("plots/profit_heatmap_demand{demand_label}.png")`
`ggsave(fig_path, plot = p)`

The R extractor does not resolve `glue(...)` calls. The variable `fig_path` is assigned
a `glue` expression, but when `ggsave(fig_path, ...)` is processed the extractor cannot
resolve `fig_path` back to a concrete path. Result: no edge emitted at all.

**Root cause**: `parser/r_extract.py` — `glue(...)` is not recognised as a
string-producing assignment in the variable-tracking logic.

---

## Bug 2 — `sprintf()` path partially unresolved (export_pdf.R — wrong path)

`pdf_path <- sprintf("results/%s_alpha%.2f.pdf", case, alpha)`
`pdf(pdf_path, width = 8, height = 6)`

An edge IS emitted, but the target path is `results/scenario_a_alpha%.2f.pdf`.
The `%s` substitution for `case = "scenario_a"` succeeds, but the `%.2f`
numeric format specifier is not substituted for `alpha = 0.05`.

**Root cause**: `parser/r_extract.py` — the `sprintf` resolver substitutes
string (`%s`) arguments but does not handle numeric format specifiers (`%d`, `%f`,
`%.Nf`, etc.).  Numeric variable values are likely not tracked, or only string
types are substituted.

---

## Bug 3 — `paste0()` multi-variable path resolves correctly (plot_results.R — OK)

`save_path <- paste0(out_dir, "/", plot_name, ".png")`
`ggsave(save_path, plot = p, dpi = 300)`

Edge emitted correctly as `plots/baseline.png`. No bug here; serves as a
baseline to show `paste0` with string-literal variables works.

---

## Bugs confirmed (do NOT fix in this task)

| ID | Pattern | Symptom |
|----|---------|---------|
| FD-03-A | `glue("path{var}")` → `ggsave(var)` | Edge missing entirely |
| FD-03-B | `sprintf("path_%s_val%.2f.pdf", str_var, num_var)` → `pdf(var)` | Edge present but numeric format specifier left unresolved in path |
