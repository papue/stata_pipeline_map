"""Unit tests for the Python parser (python_extract.py)."""
from __future__ import annotations

from pathlib import Path
import tempfile
import textwrap

import pytest

from stata_pipeline_flow.config.schema import ExclusionConfig, NormalizationConfig, ParserConfig
from stata_pipeline_flow.parser.python_extract import parse_python_file


def _parse(code: str, *, project_root: Path | None = None) -> object:
    """Parse a Python code snippet and return the ScriptParseResult."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = project_root or Path(tmpdir)
        script = root / "script.py"
        script.write_text(textwrap.dedent(code), encoding="utf-8")
        return parse_python_file(
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
# Read detection
# ---------------------------------------------------------------------------

def test_pd_read_csv_direct():
    result = _parse('import pandas as pd\ndf = pd.read_csv("data/raw/survey.csv")\n')
    assert "read_csv" in _commands(result)
    assert any("survey.csv" in p for p in _paths(result))


def test_pd_read_excel_direct():
    result = _parse('import pandas as pd\ndf = pd.read_excel("data/raw/survey.xlsx")\n')
    assert "read_excel" in _commands(result)


def test_pd_read_parquet_direct():
    result = _parse('import pandas as pd\ndf = pd.read_parquet("data/clean/survey.parquet")\n')
    assert "read_parquet" in _commands(result)


def test_open_read_default_mode():
    result = _parse('f = open("data/notes.txt")\n')
    assert "open_read" in _commands(result)
    assert any("notes.txt" in p for p in _paths(result))


def test_open_read_explicit_mode():
    result = _parse('f = open("data/notes.txt", "r")\n')
    assert "open_read" in _commands(result)


# ---------------------------------------------------------------------------
# Write detection
# ---------------------------------------------------------------------------

def test_to_csv_write():
    result = _parse('import pandas as pd\ndf.to_csv("results/output.csv")\n')
    assert "to_csv" in _commands(result)
    assert any("output.csv" in p for p in _paths(result))


def test_to_parquet_write():
    result = _parse('df.to_parquet("data/clean/survey.parquet")\n')
    assert "to_parquet" in _commands(result)


def test_savefig_method():
    result = _parse('fig.savefig("results/plot.png")\n')
    assert "savefig" in _commands(result)
    assert any("plot.png" in p for p in _paths(result))


def test_plt_savefig():
    result = _parse('import matplotlib.pyplot as plt\nplt.savefig("results/plot.png")\n')
    assert "savefig" in _commands(result)


def test_open_write():
    result = _parse('with open("results/log.txt", "w") as f:\n    f.write("hello")\n')
    assert "open_write" in _commands(result)
    assert any("log.txt" in p for p in _paths(result))


# ---------------------------------------------------------------------------
# Variable expansion
# ---------------------------------------------------------------------------

def test_variable_expansion_read():
    code = """\
        import pandas as pd
        INPUT_FILE = "data/raw/survey.csv"
        df = pd.read_csv(INPUT_FILE)
    """
    result = _parse(code)
    assert "read_csv" in _commands(result)
    assert any("survey.csv" in p for p in _paths(result))


def test_variable_expansion_write():
    code = """\
        OUTPUT = "results/summary.csv"
        df.to_csv(OUTPUT)
    """
    result = _parse(code)
    assert "to_csv" in _commands(result)
    assert any("summary.csv" in p for p in _paths(result))


# ---------------------------------------------------------------------------
# Comment stripping
# ---------------------------------------------------------------------------

def test_comment_lines_ignored():
    code = """\
        # df = pd.read_csv("dummy.csv")
        # df.to_csv("dummy_out.csv")
        x = 1
    """
    result = _parse(code)
    assert len(result.events) == 0


def test_inline_comment_stripped():
    code = 'df = pd.read_csv("data/real.csv")  # not "data/fake.csv"\n'
    result = _parse(code)
    paths = _paths(result)
    assert any("real.csv" in p for p in paths)
    assert not any("fake.csv" in p for p in paths)


# ---------------------------------------------------------------------------
# Local import tracking (child scripts)
# ---------------------------------------------------------------------------

def test_import_local_module(tmp_path):
    (tmp_path / "helpers.py").write_text("def foo(): pass\n")
    code = "import helpers\n"
    result = _parse(code, project_root=tmp_path)
    assert any("helpers.py" in c for c in result.child_scripts)


def test_from_local_module_import(tmp_path):
    utils_dir = tmp_path / "utils"
    utils_dir.mkdir()
    (utils_dir / "data.py").write_text("def load(): pass\n")
    code = "from utils.data import load\n"
    result = _parse(code, project_root=tmp_path)
    assert any("utils/data.py" in c or "utils\\data.py" in c for c in result.child_scripts)


def test_stdlib_import_not_tracked():
    """Standard library imports should not appear as child scripts."""
    result = _parse("import os\nimport json\nimport pathlib\n")
    assert len(result.child_scripts) == 0


# ---------------------------------------------------------------------------
# Import alias tracking
# ---------------------------------------------------------------------------

def test_custom_alias_read():
    """from pandas import read_csv; read_csv(...) should be detected."""
    code = """\
        from pandas import read_csv
        df = read_csv("data/raw/survey.csv")
    """
    result = _parse(code)
    assert "read_csv" in _commands(result)


# ---------------------------------------------------------------------------
# External reference filtering
# ---------------------------------------------------------------------------

def test_url_path_not_tracked():
    result = _parse('df = pd.read_csv("https://example.com/data.csv")\n')
    assert len(result.events) == 0
    # Should emit a diagnostic instead
    assert any(d.code == "external_reference" for d in result.global_warnings)


# ---------------------------------------------------------------------------
# Fixture-level smoke test
# ---------------------------------------------------------------------------

def test_fixture_python_project_parses():
    """Smoke test: fixture project scripts parse without crashing."""
    fixture_root = Path(__file__).parent / "fixtures" / "python_project"
    if not fixture_root.exists():
        pytest.skip("python_project fixture not found")

    for py_file in fixture_root.rglob("*.py"):
        result = parse_python_file(
            fixture_root,
            py_file,
            ExclusionConfig(),
            NormalizationConfig(),
            ParserConfig(),
        )
        assert result is not None
