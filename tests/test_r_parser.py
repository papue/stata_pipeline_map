"""Unit tests for the R parser (r_extract.py)."""
from __future__ import annotations

from pathlib import Path
import tempfile
import textwrap

import pytest

from data_pipeline_flow.config.schema import ExclusionConfig, NormalizationConfig, ParserConfig
from data_pipeline_flow.parser.r_extract import parse_r_file


def _parse(code: str, *, project_root: Path | None = None) -> object:
    with tempfile.TemporaryDirectory() as tmpdir:
        root = project_root or Path(tmpdir)
        script = root / "script.R"
        script.write_text(textwrap.dedent(code), encoding="utf-8")
        return parse_r_file(
            root,
            script,
            ExclusionConfig(),
            NormalizationConfig(),
            ParserConfig(),
        )


def _commands(result) -> set[str]:
    return {e.command for e in result.events}


def _paths(result) -> set[str]:
    return {p for e in result.events for p in e.normalized_paths}


# ---------------------------------------------------------------------------
# Read detection — base R
# ---------------------------------------------------------------------------

def test_read_csv_base_r():
    result = _parse('df <- read.csv("data/raw/survey.csv")\n')
    assert "read_csv" in _commands(result)
    assert any("survey.csv" in p for p in _paths(result))


def test_readRDS_first_arg():
    result = _parse('df <- readRDS("data/clean/survey_clean.rds")\n')
    assert "readRDS" in _commands(result)
    assert any("survey_clean.rds" in p for p in _paths(result))


def test_load_base_r():
    result = _parse('load("data/workspace.RData")\n')
    assert "load" in _commands(result)


# ---------------------------------------------------------------------------
# Read detection — readr / tidyverse
# ---------------------------------------------------------------------------

def test_read_csv_readr_qualified():
    result = _parse('df <- readr::read_csv("data/raw/survey.csv")\n')
    assert "read_csv_readr" in _commands(result)


def test_read_csv_readr_unqualified():
    result = _parse('library(readr)\ndf <- read_csv("data/raw/survey.csv")\n')
    assert "read_csv_readr" in _commands(result)


# ---------------------------------------------------------------------------
# Read detection — haven
# ---------------------------------------------------------------------------

def test_read_dta_haven():
    result = _parse('df <- haven::read_dta("data/clean/survey.dta")\n')
    assert "read_dta" in _commands(result)


def test_read_dta_unqualified():
    result = _parse('df <- read_dta("data/clean/survey.dta")\n')
    assert "read_dta" in _commands(result)


# ---------------------------------------------------------------------------
# Read detection — data.table
# ---------------------------------------------------------------------------

def test_fread():
    result = _parse('dt <- data.table::fread("data/raw/survey.csv")\n')
    assert "fread" in _commands(result)


# ---------------------------------------------------------------------------
# Write detection — base R
# ---------------------------------------------------------------------------

def test_write_csv_base_r():
    result = _parse('write.csv(df, "results/output.csv")\n')
    assert "write_csv" in _commands(result)
    assert any("output.csv" in p for p in _paths(result))


def test_saveRDS_positional():
    result = _parse('saveRDS(df, "results/model.rds")\n')
    assert "saveRDS" in _commands(result)
    assert any("model.rds" in p for p in _paths(result))


def test_saveRDS_keyword_arg():
    result = _parse('saveRDS(df, file = "results/model.rds")\n')
    assert "saveRDS_kw" in _commands(result)
    assert any("model.rds" in p for p in _paths(result))


# ---------------------------------------------------------------------------
# Write detection — ggplot2
# ---------------------------------------------------------------------------

def test_ggsave_first_arg():
    result = _parse('ggsave("results/plot.png", plot = p)\n')
    assert "ggsave" in _commands(result)
    assert any("plot.png" in p for p in _paths(result))


def test_ggsave_filename_kwarg():
    result = _parse('ggsave(filename = "results/plot.pdf", plot = p)\n')
    assert "ggsave_kw" in _commands(result)
    assert any("plot.pdf" in p for p in _paths(result))


def test_ggsave_qualified():
    result = _parse('ggplot2::ggsave("results/fig.png")\n')
    assert "ggsave" in _commands(result)


# ---------------------------------------------------------------------------
# Write detection — graphics devices
# ---------------------------------------------------------------------------

def test_pdf_device():
    result = _parse('pdf("results/figure.pdf")\n')
    assert "pdf" in _commands(result)


def test_png_device():
    result = _parse('png("results/figure.png")\n')
    assert "png" in _commands(result)


# ---------------------------------------------------------------------------
# Write detection — haven
# ---------------------------------------------------------------------------

def test_write_dta_haven_qualified():
    result = _parse('haven::write_dta(df, "results/clean.dta")\n')
    assert "write_dta" in _commands(result)
    assert any("clean.dta" in p for p in _paths(result))


def test_write_dta_unqualified():
    result = _parse('write_dta(df, "results/clean.dta")\n')
    assert "write_dta" in _commands(result)


# ---------------------------------------------------------------------------
# Script call detection
# ---------------------------------------------------------------------------

def test_source_call():
    result = _parse('source("01_data/load_data.R")\n')
    # On Windows, _case_fold lowercases node IDs, so compare case-insensitively.
    assert any("load_data.r" in c.lower() for c in result.child_scripts)


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def test_here_resolves():
    result = _parse('df <- read_csv(here("data", "raw", "survey.csv"))\n')
    assert any("data/raw/survey.csv" in p for p in _paths(result))


def test_here_qualified_resolves():
    result = _parse('df <- read_csv(here::here("data", "raw", "survey.csv"))\n')
    assert any("data/raw/survey.csv" in p for p in _paths(result))


def test_file_path_resolves():
    result = _parse('df <- read_csv(file.path("data", "raw", "survey.csv"))\n')
    assert any("data/raw/survey.csv" in p for p in _paths(result))


def test_paste0_resolves():
    code = """\
        BASE <- "data/raw"
        df <- read_csv(paste0(BASE, "/survey.csv"))
    """
    result = _parse(code)
    assert any("data/raw/survey.csv" in p for p in _paths(result))


def test_sprintf_single_substitution():
    result = _parse('df <- read_csv(sprintf("data/%s/survey.csv", "2024"))\n')
    assert any("data/2024/survey.csv" in p for p in _paths(result))


# ---------------------------------------------------------------------------
# Variable tracking
# ---------------------------------------------------------------------------

def test_variable_expansion_read():
    code = """\
        INPUT <- "data/raw/survey.csv"
        df <- read_csv(INPUT)
    """
    result = _parse(code)
    assert any("survey.csv" in p for p in _paths(result))


def test_variable_expansion_read_arrow():
    code = """\
        OUT_FILE <- "results/model.rds"
        saveRDS(df, OUT_FILE)
    """
    result = _parse(code)
    # saveRDS positional pattern matches variable too via vars_map
    # This tests that the variable value is used
    assert any("model.rds" in p for p in _paths(result))


# ---------------------------------------------------------------------------
# Comment stripping
# ---------------------------------------------------------------------------

def test_comment_lines_ignored():
    code = """\
        # df <- read_csv("dummy.csv")
        # write_csv(df, "dummy_out.csv")
        x <- 1
    """
    result = _parse(code)
    assert len(result.events) == 0


def test_inline_comment_stripped():
    code = 'df <- read_csv("data/real.csv")  # not "data/fake.csv"\n'
    result = _parse(code)
    paths = _paths(result)
    assert any("real.csv" in p for p in paths)
    assert not any("fake.csv" in p for p in paths)


# ---------------------------------------------------------------------------
# External reference filtering
# ---------------------------------------------------------------------------

def test_url_not_tracked():
    result = _parse('df <- read_csv("https://example.com/data.csv")\n')
    assert len(result.events) == 0
    assert any(d.code == "external_reference" for d in result.global_warnings)


# ---------------------------------------------------------------------------
# Fixture-level smoke test
# ---------------------------------------------------------------------------

def test_fixture_r_project_parses():
    fixture_root = Path(__file__).parent / "fixtures" / "r_project"
    if not fixture_root.exists():
        pytest.skip("r_project fixture not found")

    for r_file in fixture_root.rglob("*.R"):
        result = parse_r_file(
            fixture_root,
            r_file,
            ExclusionConfig(),
            NormalizationConfig(),
            ParserConfig(),
        )
        assert result is not None


# ---------------------------------------------------------------------------
# MO-26: spurious "." node — file.path(".") must not emit a node
# ---------------------------------------------------------------------------

def test_file_path_dot_no_spurious_node():
    """file.path('.') stored in a var then used in read.csv must produce no node."""
    result = _parse(
        '''
        path <- file.path(".")
        df <- read.csv(path)
        '''
    )
    paths = _paths(result)
    assert '.' not in paths, f"Spurious '.' node emitted: {paths}"
    assert not any(p in ('./', '.\\') for p in paths)


def test_paste0_dot_slash_no_spurious_node():
    """paste0('./') used directly in read.csv must not emit a bare './' node."""
    result = _parse(
        '''
        df <- read.csv(paste0("./"))
        '''
    )
    paths = _paths(result)
    assert not any(p.rstrip('/\\') in ('', '.') for p in paths), (
        f"Spurious directory node emitted: {paths}"
    )


def test_file_path_dot_with_known_suffix_resolves():
    """file.path('.', 'data', 'out.csv') is a valid path and must be emitted."""
    result = _parse(
        '''
        df <- read.csv(file.path(".", "data", "out.csv"))
        '''
    )
    paths = _paths(result)
    assert any("out.csv" in p for p in paths), f"Expected out.csv in paths: {paths}"


def test_r_spurious_dot_fixture_trigger_script():
    """trigger_dot.R in the r_spurious_dot fixture must produce no events."""
    fixture_root = Path(__file__).parent / "fixtures" / "r_spurious_dot"
    trigger = fixture_root / "scripts" / "trigger_dot.R"
    if not trigger.exists():
        pytest.skip("trigger_dot.R fixture not found")
    result = parse_r_file(
        fixture_root,
        trigger,
        ExclusionConfig(),
        NormalizationConfig(),
        ParserConfig(),
    )
    paths = _paths(result)
    assert '.' not in paths, f"Spurious '.' node emitted by trigger_dot.R: {paths}"
    assert len(result.events) == 0, f"Expected 0 events, got: {result.events}"


def test_r_spurious_dot_fixture_load_known_still_works():
    """load_known.R in the r_spurious_dot fixture must still resolve data/final.csv."""
    fixture_root = Path(__file__).parent / "fixtures" / "r_spurious_dot"
    load_known = fixture_root / "scripts" / "load_known.R"
    if not load_known.exists():
        pytest.skip("load_known.R fixture not found")
    result = parse_r_file(
        fixture_root,
        load_known,
        ExclusionConfig(),
        NormalizationConfig(),
        ParserConfig(),
    )
    paths = _paths(result)
    assert any("final.csv" in p for p in paths), (
        f"Expected data/final.csv edge from load_known.R, got: {paths}"
    )


# ---------------------------------------------------------------------------
# FD-04: glue() path resolution — ggsave(fig_path) where fig_path <- glue(...)
# ---------------------------------------------------------------------------

def test_glue_path_resolved_for_ggsave():
    """glue('plots/profit_heatmap_demand{demand_label}.png') stored in a var
    then passed to ggsave() must produce a write edge with the fully resolved path."""
    result = _parse(
        '''
        library(glue)
        demand_label <- "high"
        fig_path <- glue("plots/profit_heatmap_demand{demand_label}.png")
        p <- ggplot(mtcars, aes(mpg, cyl)) + geom_point()
        ggsave(fig_path, plot = p)
        '''
    )
    paths = _paths(result)
    assert "plots/profit_heatmap_demandhigh.png" in paths, (
        f"Expected resolved glue path in write events, got: {paths}"
    )


def test_glue_path_resolved_direction_is_write():
    """The edge from ggsave(glue_var) must be a write (script -> artifact), not a read."""
    result = _parse(
        '''
        library(glue)
        label <- "final"
        out_path <- glue("output/{label}_report.pdf")
        ggsave(out_path)
        '''
    )
    write_events = [e for e in result.events if e.command in ('ggsave',)]
    assert write_events, "Expected at least one ggsave write event"
    resolved = {p for e in write_events for p in e.normalized_paths}
    assert "output/final_report.pdf" in resolved, (
        f"Expected 'output/final_report.pdf' in write events, got: {resolved}"
    )


# ---------------------------------------------------------------------------
# FD-04: sprintf() numeric format specifier resolution
# ---------------------------------------------------------------------------

def test_sprintf_numeric_format_specifier_resolved():
    """sprintf('results/%s_alpha%.2f.pdf', case, alpha) must emit the fully resolved
    path 'results/scenario_a_alpha0.05.pdf', not leave '%.2f' unsubstituted."""
    result = _parse(
        '''
        case  <- "scenario_a"
        alpha <- 0.05
        pdf_path <- sprintf("results/%s_alpha%.2f.pdf", case, alpha)
        pdf(pdf_path, width = 8, height = 6)
        dev.off()
        '''
    )
    paths = _paths(result)
    assert "results/scenario_a_alpha0.05.pdf" in paths, (
        f"Expected fully resolved sprintf path, got: {paths}"
    )
    # Make sure we did NOT emit the partially-substituted wrong path
    assert not any("%.2f" in p for p in paths), (
        f"Found unresolved numeric format specifier in paths: {paths}"
    )


def test_sprintf_multiple_numeric_args():
    """sprintf with multiple numeric args must substitute all of them."""
    result = _parse(
        '''
        x <- 1.5
        y <- 2.0
        out <- sprintf("data/result_x%.1f_y%.1f.csv", x, y)
        write.csv(df, out)
        '''
    )
    paths = _paths(result)
    assert "data/result_x1.5_y2.0.csv" in paths, (
        f"Expected resolved multi-numeric sprintf path, got: {paths}"
    )


def test_fstring_direction_r_fixture():
    """Smoke test: all three R fixture scripts must produce the correct write edges."""
    fixture_root = Path(__file__).parent / "fixtures" / "fstring_direction_r"
    if not fixture_root.exists():
        pytest.skip("fstring_direction_r fixture not found")

    expected = {
        "plots/baseline.png",
        "plots/profit_heatmap_demandhigh.png",
        "results/scenario_a_alpha0.05.pdf",
    }

    all_paths: set[str] = set()
    for r_file in (fixture_root / "analysis").rglob("*.R"):
        res = parse_r_file(
            fixture_root,
            r_file,
            ExclusionConfig(),
            NormalizationConfig(),
            ParserConfig(),
        )
        all_paths.update(_paths(res))

    for exp in expected:
        assert exp in all_paths, (
            f"Expected edge target '{exp}' not found in R fixture. Got: {all_paths}"
        )
