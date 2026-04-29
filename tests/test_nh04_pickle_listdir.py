"""
NH-04: pickle.load + os.listdir regression tests.

Verifies that the pickle_listdir fixture produces the expected read edges for:
  - pickle.load(open(os.path.join(path, "result_0.pkl"), "rb"))  — one-line form
  - os.listdir(path) with .pkl endswith filter -> wildcard read edge
  - open(param_path, "r") + json.load -> read edge for parameters.json
  - os.listdir inside a helper function (profit_heatmap.py)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from data_pipeline_flow.config.schema import AppConfig
from data_pipeline_flow.parser.python_extract import parse_python_file

FIXTURES = Path(__file__).parent / "fixtures" / "pickle_listdir" / "analysis"
PROJECT_ROOT = Path(__file__).parent / "fixtures" / "pickle_listdir"


def _parse(filename: str):
    cfg = AppConfig()
    return parse_python_file(
        project_root=PROJECT_ROOT,
        py_file=FIXTURES / filename,
        exclusions=cfg.exclusions,
        normalization=cfg.normalization,
        parser_config=cfg.parser,
    )


def _read_paths(result) -> list[str]:
    """Return all normalized paths from read events."""
    return [
        norm
        for ev in result.events
        for norm in ev.normalized_paths
        if not ev.is_write
    ]


# ---------------------------------------------------------------------------
# extract_data.py tests
# ---------------------------------------------------------------------------

def test_pickle_load_one_line_emits_read_edge():
    """Pattern 1: pickle.load(open(os.path.join(path, "result_0.pkl"), "rb"))
    should emit a read edge containing 'result_0.pkl'."""
    result = _parse("extract_data.py")
    paths = _read_paths(result)
    assert any("result_0.pkl" in p for p in paths), (
        f"Expected read edge for 'result_0.pkl', got paths: {paths}"
    )


def test_listdir_pkl_filter_emits_wildcard_read_edge():
    """Pattern 2: os.listdir(path) with f.endswith('.pkl') filter
    should emit a wildcard read edge ending with '/*.pkl'."""
    result = _parse("extract_data.py")
    paths = _read_paths(result)
    # Should have a wildcard node with .pkl suffix
    assert any(p.endswith("/*.pkl") or p.endswith("/*.pkl".replace("/", "\\")) for p in paths), (
        f"Expected wildcard /*.pkl read edge from os.listdir, got paths: {paths}"
    )


def test_json_load_via_variable_path_emits_read_edge():
    """Pattern 3: open(param_path, "r") where param_path=os.path.join(path, "parameters.json")
    should emit a read edge containing 'parameters.json'."""
    result = _parse("extract_data.py")
    paths = _read_paths(result)
    assert any("parameters.json" in p for p in paths), (
        f"Expected read edge for 'parameters.json', got paths: {paths}"
    )


# ---------------------------------------------------------------------------
# profit_heatmap.py tests
# ---------------------------------------------------------------------------

def test_profit_heatmap_listdir_emits_wildcard_pkl_edge():
    """profit_heatmap.py: os.listdir(folder) inside load_pkl_files() with .pkl filter
    should emit a wildcard /*.pkl read edge."""
    result = _parse("profit_heatmap.py")
    paths = _read_paths(result)
    assert any("pkl" in p for p in paths), (
        f"Expected at least one .pkl read edge from profit_heatmap.py, got paths: {paths}"
    )


def test_profit_heatmap_results_base_resolved():
    """RESULTS_BASE is built via __file__ and os.path.join.
    At least one read edge should reference the 'results' or 'demand_benchmark' folder."""
    result = _parse("profit_heatmap.py")
    paths = _read_paths(result)
    assert any("results" in p or "demand_benchmark" in p for p in paths), (
        f"Expected read edge referencing 'results' directory, got paths: {paths}"
    )


# ---------------------------------------------------------------------------
# Integration: extract-edges CLI produces edges for the fixture
# ---------------------------------------------------------------------------

def test_extract_edges_fixture_produces_edges():
    """Smoke test: the full graph builder should produce at least 4 edges for
    the pickle_listdir fixture (3 patterns in extract_data + 1 in profit_heatmap)."""
    from data_pipeline_flow.config.schema import AppConfig
    from data_pipeline_flow.parser.discovery import discover_project_files
    from data_pipeline_flow.parser.multi_extract import build_graph_from_scripts

    cfg = AppConfig()
    scan = discover_project_files(PROJECT_ROOT, cfg.exclusions, cfg.normalization, cfg.languages)
    scripts = scan.script_files
    graph = build_graph_from_scripts(
        project_root=PROJECT_ROOT,
        script_files=scripts,
        exclusions=cfg.exclusions,
        parser_config=cfg.parser,
        normalization=cfg.normalization,
        classification_config=cfg.classification,
        display_config=cfg.display,
    )
    assert len(graph.edges) >= 4, (
        f"Expected at least 4 edges for pickle_listdir fixture, got {len(graph.edges)}: "
        f"{[str(e) for e in graph.edges]}"
    )
