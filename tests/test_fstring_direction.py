"""Regression tests for fstring_path edge direction fix (task FD-02) and
R glue/sprintf path resolution fixes (task FD-04), and Stata export-excel
`using`-optional fix (task FD-06).

Covers:
  1. Same-line pattern: f-string with .png/.pdf extension on a line that also has
     a write call → edge direction must be script → artifact.
  2. Two-line pattern: f-string assigned to a variable on one line; savefig on the
     next line → edge direction must be script → artifact.
  3. Read-context f-string (e.g. pd.read_parquet) → edge direction must remain
     artifact → script.
  4. (R) glue() string interpolation: glue("path/{var}.png") assigned to variable,
     then ggsave(var) → script → artifact edge with resolved path.
  5. (R) sprintf() with numeric format specifier: sprintf("results/%s_alpha%.2f.pdf",
     str_var, num_var) → script → artifact edge with fully resolved path.
  6. (Stata) export excel without `using` keyword and mixed global/local macro path
     → script → artifact edge with correct direction.
  7. (Stata) export excel with `using` keyword (backward-compat) → still works.
"""
from __future__ import annotations

from pathlib import Path

from data_pipeline_flow.config.schema import AppConfig
from data_pipeline_flow.rules.pipeline import PipelineBuilder
from data_pipeline_flow.parser.stata_extract import parse_do_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _build(project_root: Path):
    config = AppConfig(project_root=str(project_root))
    return PipelineBuilder(config).build(project_root)


# ---------------------------------------------------------------------------
# Test 1 — same-line pattern: f-string assignment with .pdf extension
# The f-string is on a line that is a plain assignment (no savefig on same line),
# but the extension heuristic should flag it as a write.
# ---------------------------------------------------------------------------

def test_fstring_pdf_extension_produces_write_edge(tmp_path: Path) -> None:
    """f-string ending in .pdf on an assignment line → script → artifact edge."""
    _write(tmp_path / 'analysis' / 'make_figure.py', '''\
import matplotlib.pyplot as plt

case = "base"
ialpha = 1
metric = "welfare"

filename = f"{case}_alpha{ialpha}_{metric}.pdf"
filepath = f"results/{filename}"
fig, ax = plt.subplots()
fig.savefig(filepath, format='pdf', bbox_inches='tight')
''')
    graph = _build(tmp_path)
    edges = {(e.source, e.target) for e in graph.edges}

    # Must have a write edge from script to the placeholder artifact
    script = 'analysis/make_figure.py'
    write_edges = [
        (src, tgt) for src, tgt in edges
        if src == script and 'pdf' in tgt
    ]
    assert write_edges, (
        f"Expected a write edge from {script} to a .pdf artifact, got edges: {edges}"
    )
    # The reversed edge must NOT exist
    reversed_edges = [
        (src, tgt) for src, tgt in edges
        if tgt == script and 'pdf' in src
    ]
    assert not reversed_edges, (
        f"Wrong-direction edge (artifact → script) still present: {reversed_edges}"
    )


# ---------------------------------------------------------------------------
# Test 2 — two-line pattern: f-string with .png extension inside os.path.join
# assignment; savefig on the next line.
# ---------------------------------------------------------------------------

def test_fstring_png_two_line_pattern_produces_write_edge(tmp_path: Path) -> None:
    """f-string ending in .png assigned to variable, savefig on next line → write edge."""
    _write(tmp_path / 'analysis' / 'heatmap.py', '''\
import os
import matplotlib.pyplot as plt

PLOTS_DIR = "plots"
label = "high"

fig, ax = plt.subplots()
save_path = os.path.join(PLOTS_DIR, f"heatmap_demand{label}.png")
fig.savefig(save_path, dpi=300, bbox_inches="tight")
''')
    graph = _build(tmp_path)
    edges = {(e.source, e.target) for e in graph.edges}

    script = 'analysis/heatmap.py'
    write_edges = [
        (src, tgt) for src, tgt in edges
        if src == script and 'png' in tgt
    ]
    assert write_edges, (
        f"Expected a write edge from {script} to a .png artifact, got edges: {edges}"
    )
    reversed_edges = [
        (src, tgt) for src, tgt in edges
        if tgt == script and 'png' in src
    ]
    assert not reversed_edges, (
        f"Wrong-direction edge (artifact → script) still present: {reversed_edges}"
    )


# ---------------------------------------------------------------------------
# Test 3 — read-context f-string: pd.read_parquet with dynamic filename
# Edge direction must remain artifact → script (read).
# ---------------------------------------------------------------------------

def test_fstring_read_context_produces_read_edge(tmp_path: Path) -> None:
    """f-string used in a read call → artifact → script edge (read direction preserved)."""
    _write(tmp_path / 'analysis' / 'loader.py', '''\
import pandas as pd

country = "us"
df = pd.read_parquet(f"data/panel_{country}.parquet")
''')
    graph = _build(tmp_path)
    edges = {(e.source, e.target) for e in graph.edges}

    script = 'analysis/loader.py'
    # Expect artifact → script (read direction)
    read_edges = [
        (src, tgt) for src, tgt in edges
        if tgt == script and 'parquet' in src
    ]
    assert read_edges, (
        f"Expected a read edge (artifact → script) for .parquet, got edges: {edges}"
    )
    # Must NOT have a write edge
    write_edges = [
        (src, tgt) for src, tgt in edges
        if src == script and 'parquet' in tgt
    ]
    assert not write_edges, (
        f"Unexpected write edge for read-context f-string: {write_edges}"
    )


# ---------------------------------------------------------------------------
# Test 4 (R) — glue() interpolation: glue("path/{var}.png") → ggsave(var)
# Bug FD-03-A: R extractor did not resolve glue() assignments.
# ---------------------------------------------------------------------------

def test_r_glue_string_produces_correct_write_edge(tmp_path: Path) -> None:
    """R glue() path stored in variable, then ggsave(var) → script → artifact edge."""
    _write(tmp_path / 'analysis' / 'heatmap.R', '''\
library(ggplot2)
library(glue)

demand_label <- "high"
fig_path <- glue("plots/profit_heatmap_demand{demand_label}.png")

p <- ggplot(mtcars, aes(mpg, cyl)) + geom_point()
ggsave(fig_path, plot = p)
''')
    graph = _build(tmp_path)
    edges = {(e.source, e.target) for e in graph.edges}

    script = 'analysis/heatmap.r'
    write_edges = [
        (src, tgt) for src, tgt in edges
        if src == script and 'png' in tgt
    ]
    assert write_edges, (
        f"Expected a write edge from {script} to a .png artifact, got edges: {edges}"
    )
    # The resolved path must contain the substituted variable value, not a raw placeholder
    resolved_targets = [tgt for src, tgt in write_edges]
    assert any('high' in tgt for tgt in resolved_targets), (
        f"Expected demand_label='high' to be resolved in target path, got: {resolved_targets}"
    )
    # No reversed edge
    reversed_edges = [
        (src, tgt) for src, tgt in edges
        if tgt == script and 'png' in src
    ]
    assert not reversed_edges, (
        f"Wrong-direction edge (artifact → script) still present: {reversed_edges}"
    )


# ---------------------------------------------------------------------------
# Test 5 (R) — sprintf() with numeric format specifier: %.2f
# Bug FD-03-B: R extractor left %.2f unresolved; only %s was substituted.
# ---------------------------------------------------------------------------

def test_r_sprintf_numeric_format_specifier_resolves_correctly(tmp_path: Path) -> None:
    """R sprintf() with %.2f numeric specifier → fully resolved path in write edge."""
    _write(tmp_path / 'analysis' / 'export_pdf.R', '''\
case  <- "scenario_a"
alpha <- 0.05

pdf_path <- sprintf("results/%s_alpha%.2f.pdf", case, alpha)
pdf(pdf_path, width = 8, height = 6)
plot(1:10)
dev.off()
''')
    graph = _build(tmp_path)
    edges = {(e.source, e.target) for e in graph.edges}

    script = 'analysis/export_pdf.r'
    write_edges = [
        (src, tgt) for src, tgt in edges
        if src == script and 'pdf' in tgt
    ]
    assert write_edges, (
        f"Expected a write edge from {script} to a .pdf artifact, got edges: {edges}"
    )
    # The %.2f specifier must be replaced with the numeric value, not left as a literal format spec
    resolved_targets = [tgt for src, tgt in write_edges]
    assert not any('%.2f' in tgt or '%' in tgt for tgt in resolved_targets), (
        f"Format specifier was not resolved in target path, got: {resolved_targets}"
    )
    assert any('0.05' in tgt for tgt in resolved_targets), (
        f"Expected alpha=0.05 to appear in resolved path, got: {resolved_targets}"
    )


# ---------------------------------------------------------------------------
# Test 6 (Stata FD-06) — export excel without `using` keyword, mixed macro path
# Bug: EXPORT_EXCEL_RE required `using` but Stata allows the path directly.
# ---------------------------------------------------------------------------

def test_stata_export_excel_without_using_produces_write_edge(tmp_path: Path) -> None:
    """Stata `export excel "${outdir}/`metric'_table.xlsx"` (no `using`) → script → artifact."""
    do_file = tmp_path / 'analysis' / 'export_results.do'
    do_file.parent.mkdir(parents=True, exist_ok=True)
    do_file.write_text(
        'global outdir "results"\n'
        'local metric  "welfare"\n'
        'use "data/estimates.dta", clear\n'
        'export excel "${outdir}/`metric\'_table.xlsx", replace firstrow(variables)\n',
        encoding='utf-8',
    )
    cfg = AppConfig()
    result = parse_do_file(
        project_root=tmp_path,
        do_file=do_file,
        exclusions=cfg.exclusions,
        normalization=cfg.normalization,
        parser_config=cfg.parser,
    )
    write_events = [ev for ev in result.events if ev.command == 'export_excel']
    assert write_events, (
        f"Expected export_excel write event but found none. All events: {result.events}"
    )
    all_write_paths = [p for ev in write_events for p in ev.normalized_paths]
    assert any('welfare_table.xlsx' in p for p in all_write_paths), (
        f"Expected 'welfare_table.xlsx' in write paths after macro expansion, "
        f"got: {all_write_paths}"
    )


# ---------------------------------------------------------------------------
# Test 7 (Stata FD-06) — export excel WITH `using` keyword (backward compat)
# The optional `(?:using\s+)?` must not break the original `using`-based form.
# ---------------------------------------------------------------------------

def test_stata_export_excel_with_using_still_produces_write_edge(tmp_path: Path) -> None:
    """Stata `export excel using "output.xlsx"` (with `using`) still produces write edge."""
    do_file = tmp_path / 'scripts' / 'export_using.do'
    do_file.parent.mkdir(parents=True, exist_ok=True)
    do_file.write_text(
        'use "data/final.dta", clear\n'
        'export excel using "results/final_export.xlsx", replace\n',
        encoding='utf-8',
    )
    cfg = AppConfig()
    result = parse_do_file(
        project_root=tmp_path,
        do_file=do_file,
        exclusions=cfg.exclusions,
        normalization=cfg.normalization,
        parser_config=cfg.parser,
    )
    write_events = [ev for ev in result.events if ev.command == 'export_excel']
    assert write_events, (
        f"Expected export_excel write event but found none. All events: {result.events}"
    )
    all_write_paths = [p for ev in write_events for p in ev.normalized_paths]
    assert any('final_export.xlsx' in p for p in all_write_paths), (
        f"Expected 'final_export.xlsx' in write paths, got: {all_write_paths}"
    )
