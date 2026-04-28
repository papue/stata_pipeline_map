"""
CSG-06 — Cross-script global propagation: Python fix.

Regression tests verifying that string constants imported via
``from <module> import NAME`` from a project-local Python file are available
when resolving f-string and variable-path expressions in the importing script.

Scenarios covered:
  1. Read edge resolves after ``from config import DATA_DIR``.
  2. Write edge resolves after ``from config import OUTPUT_DIR``.
  3. No artifact_placeholder nodes remain after propagation.
  4. No partial-resolution diagnostics are emitted.
  5. extract_module_constants() unit test.
  6. _gather_imported_constants() injects the right names.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from data_pipeline_flow.config.schema import AppConfig
from data_pipeline_flow.parser.multi_extract import build_graph_from_scripts
from data_pipeline_flow.parser.python_extract import extract_module_constants

FIXTURES = Path(__file__).parent / "fixtures"
CSG_PY_FIXTURE = FIXTURES / "cross_script_globals_python"


def _build(project_root: Path) -> object:
    """Build a GraphModel for all .py files found under project_root."""
    cfg = AppConfig()
    py_files = sorted(
        str(p.relative_to(project_root)).replace("\\", "/")
        for p in project_root.rglob("*.py")
    )
    return build_graph_from_scripts(
        project_root=project_root,
        script_files=py_files,
        exclusions=cfg.exclusions,
        parser_config=cfg.parser,
        normalization=cfg.normalization,
        classification_config=cfg.classification,
        display_config=cfg.display,
    )


def _edge_set(graph) -> set[tuple[str, str]]:
    return {(e.source, e.target) for e in graph.edges}


def _placeholder_nodes(graph) -> set[str]:
    return {nid for nid, n in graph.nodes.items() if n.node_type == "artifact_placeholder"}


# ---------------------------------------------------------------------------
# 1. Read edge resolves via imported constant
# ---------------------------------------------------------------------------

def test_python_imported_constant_resolves_read_edge():
    """DATA_DIR from config.py must resolve the read_parquet path in fit_model.py."""
    graph = _build(CSG_PY_FIXTURE)
    edges = _edge_set(graph)
    assert ("data/processed/features.parquet", "analysis/fit_model.py") in edges, (
        "Expected edge: data/processed/features.parquet → analysis/fit_model.py\n"
        f"Actual edges: {sorted(edges)}"
    )


# ---------------------------------------------------------------------------
# 2. Write edge resolves via imported constant
# ---------------------------------------------------------------------------

def test_python_imported_constant_resolves_write_edge():
    """OUTPUT_DIR from config.py must resolve the to_parquet / to_csv path."""
    graph = _build(CSG_PY_FIXTURE)
    edges = _edge_set(graph)
    # fit_model.py writes predictions.parquet
    assert ("analysis/fit_model.py", "output/results/predictions.parquet") in edges, (
        "Expected edge: analysis/fit_model.py → output/results/predictions.parquet\n"
        f"Actual edges: {sorted(edges)}"
    )
    # evaluate.py writes evaluation.csv
    assert ("analysis/evaluate.py", "output/results/evaluation.csv") in edges, (
        "Expected edge: analysis/evaluate.py → output/results/evaluation.csv\n"
        f"Actual edges: {sorted(edges)}"
    )


# ---------------------------------------------------------------------------
# 3. No placeholder nodes after propagation
# ---------------------------------------------------------------------------

def test_no_placeholder_nodes_in_python_csg_fixture():
    """After the fix, no artifact_placeholder nodes should remain."""
    graph = _build(CSG_PY_FIXTURE)
    placeholders = _placeholder_nodes(graph)
    assert not placeholders, (
        f"Unexpected placeholder nodes after Python constant propagation fix: {placeholders}"
    )


# ---------------------------------------------------------------------------
# 4. No partial-resolution diagnostics
# ---------------------------------------------------------------------------

def test_python_csg_fixture_no_partial_resolution_diagnostics():
    """No dynamic_path_partial_resolution diagnostics expected after the fix."""
    graph = _build(CSG_PY_FIXTURE)
    partial = [
        d for d in graph.diagnostics
        if d.code == "dynamic_path_partial_resolution"
    ]
    assert not partial, (
        f"Unexpected partial-resolution diagnostics: "
        f"{[(d.payload.get('script'), d.payload.get('pattern')) for d in partial]}"
    )


# ---------------------------------------------------------------------------
# 5. extract_module_constants() unit test
# ---------------------------------------------------------------------------

def test_extract_module_constants_reads_string_literals():
    """extract_module_constants should return all top-level string assignments."""
    config_file = CSG_PY_FIXTURE / "config.py"
    constants = extract_module_constants(config_file)
    assert constants.get("DATA_DIR") == "data/processed", (
        f"Expected DATA_DIR='data/processed', got {constants.get('DATA_DIR')!r}"
    )
    assert constants.get("OUTPUT_DIR") == "output/results", (
        f"Expected OUTPUT_DIR='output/results', got {constants.get('OUTPUT_DIR')!r}"
    )


# ---------------------------------------------------------------------------
# 6. extract_module_constants() — missing file returns empty dict
# ---------------------------------------------------------------------------

def test_extract_module_constants_missing_file_returns_empty(tmp_path):
    """extract_module_constants must return {} for a non-existent file."""
    result = extract_module_constants(tmp_path / "nonexistent.py")
    assert result == {}
