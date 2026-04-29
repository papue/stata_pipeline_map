"""Unit tests for the Python parser (python_extract.py)."""
from __future__ import annotations

from pathlib import Path
import tempfile
import textwrap

import pytest

from data_pipeline_flow.config.schema import ExclusionConfig, NormalizationConfig, ParserConfig
from data_pipeline_flow.parser.python_extract import parse_python_file


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
# Out-of-root node ID: regression tests for NH-02
# ---------------------------------------------------------------------------

def test_abspath_join_write_produces_edge(tmp_path: Path):
    """os.path.abspath(os.path.join(__script_dir__, '..', '..', 'store')) should
    be resolved so that .to_parquet(save_path) emits a write edge."""
    (tmp_path / "analysis").mkdir()
    script = tmp_path / "analysis" / "extract.py"
    code = textwrap.dedent("""\
        import os
        import pandas as pd
        _root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'results_store'))
        save_path = os.path.join(_root, 'all_results.parquet')
        df = pd.DataFrame()
        df.to_parquet(save_path, index=False)
    """)
    script.write_text(code, encoding="utf-8")
    result = parse_python_file(
        tmp_path,
        script,
        ExclusionConfig(),
        NormalizationConfig(),
        ParserConfig(),
    )
    write_events = [e for e in result.events if e.is_write]
    assert len(write_events) == 1, f"Expected 1 write event, got {write_events}"
    node_id = write_events[0].normalized_paths[0]
    assert "results_store" in node_id
    assert "all_results.parquet" in node_id


def test_out_of_root_writer_reader_share_node_id(tmp_path: Path):
    """Writer using os.path.abspath(os.path.join(__file__, '..', '..', 'store'))
    and reader using __script_dir__ + '../../store' must produce the same node ID."""
    (tmp_path / "analysis").mkdir()

    writer = tmp_path / "analysis" / "extract.py"
    writer.write_text(textwrap.dedent("""\
        import os, pandas as pd
        _root = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'store'))
        save_path = os.path.join(_root, 'out.parquet')
        pd.DataFrame().to_parquet(save_path)
    """), encoding="utf-8")

    reader = tmp_path / "analysis" / "generate.py"
    reader.write_text(textwrap.dedent("""\
        import os, pandas as pd
        _script_dir = os.path.dirname(os.path.abspath(__file__))
        data_path = os.path.join(_script_dir, '..', '..', 'store')
        df = pd.read_parquet(os.path.join(data_path, 'out.parquet'))
    """), encoding="utf-8")

    writer_result = parse_python_file(tmp_path, writer, ExclusionConfig(), NormalizationConfig(), ParserConfig())
    reader_result = parse_python_file(tmp_path, reader, ExclusionConfig(), NormalizationConfig(), ParserConfig())

    write_paths = {p for e in writer_result.events if e.is_write for p in e.normalized_paths}
    read_paths = {p for e in reader_result.events if not e.is_write for p in e.normalized_paths}

    assert write_paths, "Writer produced no events"
    assert read_paths, "Reader produced no events"
    shared = write_paths & read_paths
    assert shared, (
        f"Writer and reader produced different node IDs: write={write_paths}, read={read_paths}"
    )


def test_fixture_out_of_root_nodeid_produces_connecting_edge():
    """Integration: the out_of_root_nodeid fixture should have a connecting edge
    between extract_data.py and generate_graphs.py via results_store/all_results.parquet."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
    from data_pipeline_flow.config.schema import AppConfig
    from data_pipeline_flow.rules.pipeline import PipelineBuilder

    fixture_root = Path(__file__).parent / "fixtures" / "out_of_root_nodeid"
    if not fixture_root.exists():
        pytest.skip("out_of_root_nodeid fixture not found")

    config = AppConfig(project_root=str(fixture_root))
    graph = PipelineBuilder(config).build(fixture_root)

    node_ids = set(graph.nodes.keys())
    assert "results_store/all_results.parquet" in node_ids, (
        f"Shared data node missing from graph. Nodes: {node_ids}"
    )
    edge_pairs = {(e.source, e.target) for e in graph.edges}
    assert ("analysis/extract_data.py", "results_store/all_results.parquet") in edge_pairs, (
        f"Missing write edge from extract_data.py. Edges: {edge_pairs}"
    )
    assert ("results_store/all_results.parquet", "analysis/generate_graphs.py") in edge_pairs, (
        f"Missing read edge to generate_graphs.py. Edges: {edge_pairs}"
    )


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
