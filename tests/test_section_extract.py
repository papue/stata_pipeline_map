"""Unit and integration tests for parser/section_extract.py."""
from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile

import pytest

from data_pipeline_flow.parser.section_extract import (
    Section,
    _infer_level,
    extract_sections,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_EXT = {"stata": ".do", "python": ".py", "r": ".R"}


def _sections_from_lines(lines: list[str], lang: str) -> list[Section]:
    """Write lines to a temp file, call extract_sections, return result."""
    suffix = _EXT.get(lang, f".{lang}")
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=suffix, delete=False, encoding="utf-8"
    ) as f:
        f.write("\n".join(lines))
        path = pathlib.Path(f.name)
    result = extract_sections(path, lang)
    path.unlink(missing_ok=True)
    return result


def _one(line: str, lang: str) -> list[Section]:
    return _sections_from_lines([line], lang)


# ---------------------------------------------------------------------------
# Stata positive cases
# ---------------------------------------------------------------------------

class TestStataPositive:
    def test_plain_numbered(self):
        result = _one("* 1. Prepare data", "stata")
        assert result == [Section(1, 1, "1. Prepare data")]

    def test_sub_numbered(self):
        result = _one("* 1.2 Filter outliers", "stata")
        assert result == [Section(1, 2, "1.2 Filter outliers")]

    def test_deep_numbered_level_capped_at_3(self):
        result = _one("* 1.2.3 Remove duplicates", "stata")
        assert result == [Section(1, 3, "1.2.3 Remove duplicates")]

    def test_letter_numbered(self):
        result = _one("* 1.A Robustness", "stata")
        assert result == [Section(1, 2, "1.A Robustness")]

    def test_inline_decorated_with_stars(self):
        result = _one("*** 1. Title ***", "stata")
        assert result == [Section(1, 1, "1. Title")]

    def test_sandwiched_header(self):
        """Decorator + header + decorator: only the inner title line is emitted."""
        sections = _sections_from_lines(["*****", "* 1. Title", "*****"], "stata")
        assert sections == [Section(2, 1, "1. Title")]

    def test_double_slash(self):
        result = _one("// 1. Prepare data", "stata")
        assert result == [Section(1, 1, "1. Prepare data")]

    def test_decorator_star_only_is_skipped(self):
        assert _one("*****************************", "stata") == []

    def test_decorator_star_dash_is_skipped(self):
        assert _one("*---------------------", "stata") == []


# ---------------------------------------------------------------------------
# Python positive cases
# ---------------------------------------------------------------------------

class TestPythonPositive:
    def test_double_hash_numbered(self):
        result = _one("## 1. Load data", "python")
        assert result == [Section(1, 1, "1. Load data")]

    def test_triple_hash_sub_numbered(self):
        result = _one("### 2.1 Merge", "python")
        assert result == [Section(1, 2, "2.1 Merge")]

    def test_decorated_equals(self):
        result = _one("# ===== 1. Load data =====", "python")
        assert result == [Section(1, 1, "1. Load data")]

    def test_decorated_dash(self):
        result = _one("# ---- 2. Run models ----", "python")
        assert result == [Section(1, 1, "2. Run models")]

    def test_cell_marker_with_title(self):
        result = _one("# %% 1. Load data", "python")
        assert result == [Section(1, 1, "1. Load data")]

    def test_notebook_cell_marker(self):
        result = _one("# In[3]:", "python")
        assert result == [Section(1, 1, "In[3]:")]

    def test_empty_cell_marker_emits_untitled(self):
        """Bare '# %%' emits an '(untitled cell)' section (cell boundary visible)."""
        result = _one("# %% ", "python")
        assert result == [Section(1, 1, "(untitled cell)")]


# ---------------------------------------------------------------------------
# R positive cases
# ---------------------------------------------------------------------------

class TestRPositive:
    def test_rstudio_trailing_dashes(self):
        result = _one("## 1. Load data ----", "r")
        assert result == [Section(1, 1, "1. Load data")]

    def test_rstudio_trailing_hashes(self):
        result = _one("# Prepare data ####", "r")
        assert result == [Section(1, 1, "Prepare data")]

    def test_decorated_equals(self):
        result = _one("# ==== 2.1 Merge ====", "r")
        assert result == [Section(1, 2, "2.1 Merge")]

    def test_multi_hash_sub_numbered(self):
        result = _one("### 1.2 Subsection ###", "r")
        assert result == [Section(1, 2, "1.2 Subsection")]


# ---------------------------------------------------------------------------
# Level inference
# ---------------------------------------------------------------------------

class TestInferLevel:
    def test_top_level_numbered(self):
        assert _infer_level("1. Prepare") == 1

    def test_sub_numbered(self):
        assert _infer_level("1.2 Filter") == 2

    def test_deep_numbered(self):
        assert _infer_level("1.2.3 Remove") == 3

    def test_letter_top_level(self):
        assert _infer_level("A. Appendix") == 1

    def test_letter_sub(self):
        assert _infer_level("A.1 Sub") == 2

    def test_plain_title_defaults_to_1(self):
        assert _infer_level("Prepare data") == 1

    def test_notebook_cell_title_defaults_to_1(self):
        assert _infer_level("In[3]:") == 1


# ---------------------------------------------------------------------------
# Negative cases (must return empty list)
# ---------------------------------------------------------------------------

class TestNegativeCases:
    def test_python_inline_comment_assignment(self):
        assert _one("# x = 5  # assign x", "python") == []

    def test_stata_note_comment(self):
        assert _one("* NOTE: check this later", "stata") == []

    def test_stata_use_command(self):
        assert _one("use data/panel.dta, clear", "stata") == []

    def test_stata_save_command(self):
        assert _one("save data/results.dta, replace", "stata") == []

    def test_python_shebang(self):
        assert _one("#!/usr/bin/env python", "python") == []

    def test_r_r_output_line(self):
        assert _one("# [1] 'hello'", "r") == []

    # --- FP-01: IPython cell magics must NOT be detected as sections ---

    def test_python_ipython_magic_time(self):
        """# %%time is an IPython magic, not a cell title."""
        assert _one("# %%time", "python") == []

    def test_python_ipython_magic_timeit(self):
        """# %%timeit is an IPython magic, not a cell title."""
        assert _one("# %%timeit", "python") == []

    def test_python_ipython_magic_capture(self):
        """# %%capture is an IPython magic, not a cell title."""
        assert _one("# %%capture", "python") == []

    # --- FP-02: R/Python console output lines must NOT be detected as sections ---

    def test_python_multi_hash_r_console_output(self):
        """## [1] 0.234 looks like R output pasted into a Python script — not a section."""
        assert _one("## [1] 0.234", "python") == []

    def test_r_multi_hash_console_output_numeric(self):
        """## [1] TRUE is R console output, not a section header."""
        assert _one("## [1] TRUE", "r") == []

    def test_r_multi_hash_console_output_string(self):
        """## [1] \"some string\" is R console output, not a section header."""
        assert _one('## [1] "some string"', "r") == []

    # --- FN-01: Stata decorated numbered headers must be detected ---

    def test_stata_inline_decorated_dash_numbered(self):
        """* -- 1. Preparation -- is a valid numbered header with dash decoration."""
        result = _one("* -- 1. Preparation --", "stata")
        assert result == [Section(1, 1, "1. Preparation")]

    def test_stata_inline_decorated_equals_numbered(self):
        """* === 1. Section === is a valid numbered header with equals decoration."""
        result = _one("* === 1. Section ===", "stata")
        assert result == [Section(1, 1, "1. Section")]

    def test_stata_inline_decorated_dash_subnumbered(self):
        """* --- 1.2 Subsection --- is a valid sub-header with dash decoration."""
        result = _one("* --- 1.2 Subsection ---", "stata")
        assert result == [Section(1, 2, "1.2 Subsection")]


# ---------------------------------------------------------------------------
# Title cleaning
# ---------------------------------------------------------------------------

class TestTitleCleaning:
    def test_stars_stripped_from_stata(self):
        s = _one("*** 1. Prepare data ***", "stata")
        assert s and s[0].title == "1. Prepare data"

    def test_rstudio_trailing_dashes_stripped(self):
        s = _one("## 1. Load data ----", "r")
        assert s and s[0].title == "1. Load data"

    def test_no_surrounding_whitespace_in_title(self):
        s = _one("*   1. Clean data   *", "stata")
        # If it matches, the title must be stripped
        if s:
            assert s[0].title == s[0].title.strip()

    def test_python_cell_title_stripped(self):
        s = _one("# ===== Load data =====", "python")
        if s:
            assert s[0].title == "Load data"


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_unknown_extension_returns_empty(self):
        """Files with unrecognised extensions return []."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".txt", delete=False, encoding="utf-8"
        ) as f:
            f.write("# 1. Some heading\n")
            path = pathlib.Path(f.name)
        result = extract_sections(path)  # auto detect
        path.unlink(missing_ok=True)
        assert result == []

    def test_empty_file_returns_empty(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".do", delete=False, encoding="utf-8"
        ) as f:
            f.write("")
            path = pathlib.Path(f.name)
        result = extract_sections(path, "stata")
        path.unlink(missing_ok=True)
        assert result == []

    def test_multiple_sections_in_order(self):
        lines = [
            "* 1. First section",
            "use data.dta",
            "* 2. Second section",
            "save results.dta",
            "* 2.1 Sub section",
        ]
        result = _sections_from_lines(lines, "stata")
        assert len(result) == 3
        assert result[0] == Section(1, 1, "1. First section")
        assert result[1] == Section(3, 1, "2. Second section")
        assert result[2] == Section(5, 2, "2.1 Sub section")

    def test_line_numbers_are_1_based(self):
        lines = ["use data.dta", "", "* 1. Prepare data"]
        result = _sections_from_lines(lines, "stata")
        assert result == [Section(3, 1, "1. Prepare data")]

    def test_auto_language_detect_stata(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".do", delete=False, encoding="utf-8"
        ) as f:
            f.write("* 1. Prepare data\n")
            path = pathlib.Path(f.name)
        result = extract_sections(path)  # auto detect
        path.unlink(missing_ok=True)
        assert result == [Section(1, 1, "1. Prepare data")]

    def test_auto_language_detect_python(self):
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        ) as f:
            f.write("## 1. Load data\n")
            path = pathlib.Path(f.name)
        result = extract_sections(path)  # auto detect
        path.unlink(missing_ok=True)
        assert result == [Section(1, 1, "1. Load data")]

    def test_section_dataclass_is_frozen(self):
        s = Section(1, 1, "Title")
        with pytest.raises((AttributeError, TypeError)):
            s.title = "Other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Integration: fixture golden test
# ---------------------------------------------------------------------------

_FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "sections_fixture"
_VENV_PYTHON = pathlib.Path(__file__).parent.parent / ".venv" / "Scripts" / "python.exe"
# Fallback for non-Windows
if not _VENV_PYTHON.exists():
    _VENV_PYTHON = pathlib.Path(__file__).parent.parent / ".venv" / "bin" / "python"


def test_sections_fixture_golden():
    """CLI output on sections_fixture must match expected_sections.json."""
    expected_path = _FIXTURE / "expected_sections.json"
    result = subprocess.run(
        [
            str(_VENV_PYTHON),
            "-m",
            "data_pipeline_flow.cli.main",
            "extract-sections",
            "--project-root",
            str(_FIXTURE),
            "--output",
            "-",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, f"CLI failed:\n{result.stderr}"
    actual = json.loads(result.stdout)
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert actual == expected


# ---------------------------------------------------------------------------
# TOC deduplication regression tests
# ---------------------------------------------------------------------------

from data_pipeline_flow.parser.section_extract import _suppress_toc_block  # noqa: E402


class TestTocSuppression:
    """Regression tests for _suppress_toc_block and the full extract_sections pipeline."""

    # --- Case 2: Standard TOC (Python) ---

    def test_standard_toc_python_suppressed(self):
        """TOC cluster at top of a Python file is suppressed; real headers kept."""
        lines = [
            "# Table of contents",
            "## 1. Load data",
            "## 2. Process data",
            "## 3. Save results",
            "",
            "import pandas as pd",
            "",
            "## 1. Load data",
            "df = pd.read_csv('data/input.csv')",
            "",
            "## 2. Process data",
            "df = df.dropna()",
            "",
            "## 3. Save results",
            "df.to_csv('data/output.csv')",
        ]
        result = _sections_from_lines(lines, "python")
        titles_by_line = {s.line: s.title for s in result}
        # TOC lines (2, 3, 4) must be gone
        assert 2 not in titles_by_line
        assert 3 not in titles_by_line
        assert 4 not in titles_by_line
        # Real headers kept
        assert titles_by_line.get(8) == "1. Load data"
        assert titles_by_line.get(11) == "2. Process data"
        assert titles_by_line.get(14) == "3. Save results"

    # --- Case 2: Standard TOC (Stata) ---

    def test_standard_toc_stata_suppressed(self):
        """TOC cluster at top of a Stata file is suppressed; real headers kept."""
        lines = [
            "* ====================================",
            "* Table of contents",
            "* 1. Load and clean data",
            "* 2. Run regressions",
            "* 3. Export tables",
            "* ====================================",
            "",
            "use \"data/input.dta\", clear",
            "",
            "* 1. Load and clean data",
            "drop if missing(y)",
            "",
            "* 2. Run regressions",
            "reg y x1 x2",
            "",
            "* 3. Export tables",
            "esttab using \"results/regs.tex\", replace",
        ]
        result = _sections_from_lines(lines, "stata")
        titles_by_line = {s.line: s.title for s in result}
        # TOC lines (3, 4, 5) must be gone
        assert 3 not in titles_by_line
        assert 4 not in titles_by_line
        assert 5 not in titles_by_line
        # Real headers kept
        assert titles_by_line.get(10) == "1. Load and clean data"
        assert titles_by_line.get(13) == "2. Run regressions"
        assert titles_by_line.get(16) == "3. Export tables"

    # --- Case 1: Repeated heading without TOC keyword (Option B dedup) ---

    def test_legitimate_repeated_heading_option_b_keeps_last(self):
        """Two identical headings spread across a file: Option B (exact-title dedup)
        keeps only the last occurrence (highest line number).

        There is no TOC keyword so Option A does not fire.  Option B fires because
        the title is an exact duplicate and keeps only the later occurrence.
        """
        lines = [
            "import pandas as pd",
            "",
            "## 1. Setup",
            "df = pd.read_csv('data/phase1_input.csv')",
            "x = df.groupby('id').mean()",
            "",
            "# lots of phase 1 code",
            "",
            "## 1. Setup",
            "df2 = pd.read_csv('data/phase2_input.csv')",
        ]
        result = _sections_from_lines(lines, "python")
        assert len(result) == 1
        assert result[0] == Section(9, 1, "1. Setup")

    # --- Case 3: Mixed TOC where the TOC keyword is on a single-hash line ---

    def test_mixed_toc_single_hash_keyword_option_b_dedup(self):
        """TOC keyword is on a single '#' line (not matched by Option A's ##+ detector).

        Option A does not fire (the ##-run of 3 lines has no TOC keyword in it).
        Option B deduplicates the exact-title entries, keeping last occurrence.
        The unique TOC-only title "0. Helper functions" is retained at L2.
        """
        lines = [
            "# Table of contents:",
            "## 0. Helper functions",
            "## 1. Load data",
            "## 2. Process data",
            "",
            "import pandas as pd",
            "",
            "## 1. Load data",
            "df = pd.read_csv('data/input.csv')",
            "",
            "## 2. Process data",
            "df = df.dropna()",
        ]
        result = _sections_from_lines(lines, "python")
        lines_found = {s.line for s in result}
        # Unique TOC title kept (not a duplicate)
        assert 2 in lines_found   # 0. Helper functions (unique, no real-header match)
        # Exact duplicates: only last occurrence kept
        assert 3 not in lines_found  # TOC: 1. Load data (earlier duplicate, dropped)
        assert 4 not in lines_found  # TOC: 2. Process data (earlier duplicate, dropped)
        assert 8 in lines_found   # 1. Load data (last occurrence, kept)
        assert 11 in lines_found  # 2. Process data (last occurrence, kept)

    # --- Case 4: Single-entry duplicate (Option B dedup: keep last) ---

    def test_single_entry_duplicate_option_b_keeps_last(self):
        """A single exact-duplicate pair with no TOC keyword: Option B keeps only last.

        Option A does not fire (only 1 consecutive ##-line before a gap, no keyword).
        Option B fires and keeps only the last (highest line number) occurrence.
        """
        lines = [
            "## 1. Load data",
            "",
            "import pandas as pd",
            "",
            "## 1. Load data",
            "df = pd.read_csv('data/input.csv')",
        ]
        result = _sections_from_lines(lines, "python")
        assert len(result) == 1
        assert result[0].line == 5

    # --- _suppress_toc_block unit test: empty input ---

    def test_suppress_toc_block_empty(self):
        assert _suppress_toc_block([], [], "python") == []

    # --- _suppress_toc_block unit test: no duplicates → unchanged ---

    def test_suppress_toc_block_no_duplicates(self):
        sections = [
            Section(1, 1, "A"),
            Section(5, 1, "B"),
            Section(10, 1, "C"),
        ]
        assert _suppress_toc_block(sections, [], "python") == sections

    # --- NH-10 regression: extract_data.py fixture (### TOC block) ---

    def test_nh10_extract_data_toc_suppressed(self):
        """extract_data.py fixture: ### TOC block (L1-L5) suppressed; real headers kept."""
        lines = [
            "### Table of contents",
            "### 0. Helper functions",
            "###     0.1 Check Constant Action",
            "### 1. Collect data",
            "### 2. Save results",
            "",
            "# test comment",
            "",
            "### 0. Helper functions",
            "",
            "def helper():",
            "    pass",
            "",
            "### 0.1 Check Constant Action",
            "",
            "def check_constant(data):",
            "    return data",
            "",
            "###     0.2 Validate data",
            "",
            "def validate(df):",
            "    return df",
            "",
            "### 1. Collect data",
            "",
            "data = [1, 2, 3]",
            "",
            "### 2. Save results",
        ]
        result = _sections_from_lines(lines, "python")
        lines_found = {s.line: s.title for s in result}
        # TOC block (L1-L5) suppressed
        assert 1 not in lines_found
        assert 2 not in lines_found
        assert 3 not in lines_found
        assert 4 not in lines_found
        assert 5 not in lines_found
        # Real headers present
        assert lines_found.get(9) == "0. Helper functions"
        assert lines_found.get(14) == "0.1 Check Constant Action"
        assert lines_found.get(19) == "0.2 Validate data"
        assert lines_found.get(24) == "1. Collect data"
        assert lines_found.get(28) == "2. Save results"

    # --- NH-10 regression: generate_output.py fixture (near-duplicate) ---

    def test_nh10_generate_output_near_duplicate_retained(self):
        """generate_output.py fixture: TOC 'Boxplots' suppressed; real 'Boxplots - by case' kept."""
        lines = [
            "### Table of contents",
            "### 1. Import data",
            "### 2. Boxplots",
            "###     2.1 Define Function",
            "###     2.2 Generate Figures",
            "### 3. Boxplots - comparing cases",
            "",
            "# test",
            "",
            "### 1. Import data",
            "",
            "import pandas as pd",
            "df = pd.read_csv('results/output.csv')",
            "",
            "### 2. Boxplots - by case",
            "",
            "import matplotlib.pyplot as plt",
            "",
            "### 2.1 Define Function",
            "",
            "def make_boxplot(df):",
            "    fig, ax = plt.subplots()",
            "    return fig, ax",
            "",
            "### 2.2 Generate Figures",
            "",
            "fig, ax = make_boxplot(df)",
            "plt.savefig('output/boxplot.png')",
            "",
            "### 3. Boxplots - comparing cases",
        ]
        result = _sections_from_lines(lines, "python")
        lines_found = {s.line: s.title for s in result}
        # Entire TOC block (L1-L6) suppressed including the "2. Boxplots" near-duplicate
        for toc_line in range(1, 7):
            assert toc_line not in lines_found, f"TOC line {toc_line} should be suppressed"
        # Real headers present
        assert lines_found.get(10) == "1. Import data"
        assert lines_found.get(15) == "2. Boxplots - by case"  # near-dupe: different title, kept
        assert lines_found.get(19) == "2.1 Define Function"
        assert lines_found.get(25) == "2.2 Generate Figures"
        assert lines_found.get(30) == "3. Boxplots - comparing cases"

    # --- NH-10 regression: no-TOC file unaffected ---

    def test_nh10_no_toc_file_unaffected(self):
        """A file with no TOC block is unaffected by Option A and Option B."""
        lines = [
            "import pandas as pd",
            "",
            "## 1. Load data",
            "df = pd.read_csv('data/input.csv')",
            "",
            "## 2. Process data",
            "df = df.dropna()",
            "",
            "## 3. Save results",
            "df.to_csv('data/output.csv')",
        ]
        result = _sections_from_lines(lines, "python")
        assert len(result) == 3
        assert result[0] == Section(3, 1, "1. Load data")
        assert result[1] == Section(6, 1, "2. Process data")
        assert result[2] == Section(9, 1, "3. Save results")

    # --- NH-10 regression: R TOC block (## ---- markers) ---

    def test_nh10_r_toc_block_suppressed(self):
        """R file: TOC entries using ## ---- markers are suppressed."""
        lines = [
            "# Table of contents:",
            "## 1. Load data ----",
            "## 2. Fit models ----",
            "## 3. Export results ----",
            "",
            "library(readr)",
            "",
            "## 1. Load data ----",
            "df <- read_csv('data/input.csv')",
            "",
            "## 2. Fit models ----",
            "model <- lm(y ~ x, data = df)",
            "",
            "## 3. Export results ----",
            "write_csv(as.data.frame(coef(model)), 'results/coefs.csv')",
        ]
        result = _sections_from_lines(lines, "r")
        lines_found = {s.line: s.title for s in result}
        # TOC entries suppressed
        assert 2 not in lines_found
        assert 3 not in lines_found
        assert 4 not in lines_found
        # Real headers kept
        assert lines_found.get(8) == "1. Load data"
        assert lines_found.get(11) == "2. Fit models"
        assert lines_found.get(14) == "3. Export results"


# ---------------------------------------------------------------------------
# NH-12 regression: indented `# ---` suppressed; column-0 markers retained
# ---------------------------------------------------------------------------

import pathlib  # noqa: E402 (already imported above but needed here for clarity)


class TestNH12InlineCommentFix:
    """Regression tests for NH-12: indented # --- ... --- must not be section headers."""

    # --- Python: indented # --- inside function body is suppressed ---

    def test_python_indented_dash_comment_suppressed(self):
        """    # --- Compute statistics --- inside a function body is NOT a section."""
        assert _one("    # --- Compute statistics ---", "python") == []

    def test_python_indented_dash_comment_tab_suppressed(self):
        """\\t# --- Internal step --- (tab-indented) is NOT a section."""
        assert _one("\t# --- Internal step ---", "python") == []

    def test_python_indented_equals_comment_suppressed(self):
        """    # ===== Setup ===== indented is NOT a section."""
        assert _one("    # ===== Setup =====", "python") == []

    # --- Python: column-0 # --- is still a section (backward compat) ---

    def test_python_column0_dash_section_retained(self):
        """# --- Section Title --- at column 0 IS still a section header."""
        result = _one("# --- Section Title ---", "python")
        assert result == [Section(1, 1, "Section Title")]

    def test_python_column0_equals_section_retained(self):
        """# ===== My Section ===== at column 0 IS still a section header."""
        result = _one("# ===== My Section =====", "python")
        assert result == [Section(1, 1, "My Section")]

    # --- Python: ### at column 0 is always retained (triple-hash pattern unaffected) ---

    def test_python_triple_hash_column0_retained(self):
        """### 1. Load data at column 0 IS a section (triple-hash pattern, not affected by fix)."""
        result = _one("### 1. Load data", "python")
        assert result == [Section(1, 1, "1. Load data")]

    # --- Python: ## testing at module level (column 0) — documented behavior ---

    def test_python_double_hash_module_level_detected(self):
        """## testing at column 0 (module level) IS detected by the multi-hash pattern.

        This is intentional: ## at column 0 is treated as a section header.
        The `## testing` case in generate_graphs.py is borderline (commented-out code),
        but the indentation filter does not suppress column-0 ## lines.
        See FINDINGS.md: this is a documented, accepted behavior.
        """
        result = _one("## testing", "python")
        assert result == [Section(1, 1, "testing")]

    # --- Python: full-file integration (NH-12 fixture) ---

    def test_python_nh12_generate_graphs_fixture(self):
        """generate_graphs.py fixture: indented # --- sections eliminated; ## testing kept."""
        fixture = (
            pathlib.Path(__file__).parent
            / "fixtures"
            / "inline_comment_sections"
            / "analysis"
            / "generate_graphs.py"
        )
        from data_pipeline_flow.parser.section_extract import extract_sections
        result = extract_sections(fixture, "python")
        titles = [s.title for s in result]
        # All indented # --- false positives must be gone
        assert "Compute statistics" not in titles
        assert "Draw box" not in titles
        assert "Modern Nord-Style Colours" not in titles
        assert "Price trajectories" not in titles
        assert "Quantity effect curves" not in titles
        assert "Quantity effect areas" not in titles
        assert "Formatting" not in titles
        # ## testing at module level is retained (column-0, intentional)
        assert "testing" in titles
        # Only one section total
        assert len(result) == 1

    def test_python_nh12_clean_script_fixture(self):
        """clean_script.py fixture: ### sections still correctly detected (3 entries)."""
        fixture = (
            pathlib.Path(__file__).parent
            / "fixtures"
            / "inline_comment_sections"
            / "analysis"
            / "clean_script.py"
        )
        from data_pipeline_flow.parser.section_extract import extract_sections
        result = extract_sections(fixture, "python")
        assert len(result) == 3
        assert result[0] == Section(1, 1, "1. Load data")
        assert result[1] == Section(6, 1, "2. Clean")
        assert result[2] == Section(11, 1, "3. Save")

    # --- R: indented # --- inside function body is suppressed ---

    def test_r_indented_dash_comment_suppressed(self):
        """  # --- internal step --- inside an R function body is NOT a section."""
        assert _one("  # --- internal step ---", "r") == []

    # --- R: column-0 # --- is still a section ---

    def test_r_column0_dash_section_retained(self):
        """# --- Load data --- at column 0 IS a section in R."""
        result = _one("# --- Load data ---", "r")
        assert result == [Section(1, 1, "Load data")]

    # --- R: RStudio trailing-marker # Title ---- is always retained (pattern #1 unaffected) ---

    def test_r_rstudio_trailing_marker_retained(self):
        """## Load data ---- (RStudio folding marker) is always a section regardless."""
        result = _one("## Load data ----", "r")
        assert len(result) == 1
        assert result[0].title == "Load data"

    # --- R: function body scenario ---

    def test_r_function_body_indented_not_section(self):
        """Full R snippet: indented # --- is suppressed; ## ---- section is kept."""
        lines = [
            "my_function <- function(df) {",
            "  # --- internal step ---",
            "  df <- df[complete.cases(df), ]",
            "  df",
            "}",
            "",
            "## ---- Load data ----",
            "df <- read.csv(\"data.csv\")",
        ]
        result = _sections_from_lines(lines, "r")
        titles = [s.title for s in result]
        assert "internal step" not in titles
        # The ## ---- Load data ---- line is detected (RStudio trailing-marker pattern)
        assert any("Load data" in t for t in titles)
