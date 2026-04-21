"""Unit tests for the R parser (r_extract.py)."""
from __future__ import annotations

from pathlib import Path
import tempfile
import textwrap

import pytest

from stata_pipeline_flow.config.schema import ExclusionConfig, NormalizationConfig, ParserConfig
from stata_pipeline_flow.parser.r_extract import parse_r_file


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
