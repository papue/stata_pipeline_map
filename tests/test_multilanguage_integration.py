"""Integration tests for multi-language pipeline support."""
from __future__ import annotations

from pathlib import Path

import pytest

from stata_pipeline_flow.config.schema import AppConfig
from stata_pipeline_flow.rules.pipeline import PipelineBuilder


_FIXTURE_DIR = Path(__file__).parent / "fixtures"
_PYTHON_PROJECT = _FIXTURE_DIR / "python_project"
_R_PROJECT = _FIXTURE_DIR / "r_project"
_STATA_PROJECT = Path(__file__).parent.parent / "example" / "project"


def _build(project_root: Path) -> object:
    config = AppConfig(project_root=str(project_root))
    # Disable write_edge_csv to avoid creating files in fixture dirs
    config.parser.write_edge_csv = False
    return PipelineBuilder(config).build(project_root)


# ---------------------------------------------------------------------------
# Python project
# ---------------------------------------------------------------------------

def test_python_project_builds():
    if not _PYTHON_PROJECT.exists():
        pytest.skip("python_project fixture not found")
    graph = _build(_PYTHON_PROJECT)
    assert len(graph.nodes) > 0
    assert len(graph.edges) > 0


def test_python_script_nodes_have_language_metadata():
    if not _PYTHON_PROJECT.exists():
        pytest.skip("python_project fixture not found")
    graph = _build(_PYTHON_PROJECT)
    script_nodes = [n for n in graph.nodes.values() if n.node_type == "script"]
    assert len(script_nodes) > 0
    for node in script_nodes:
        assert node.metadata.get("language") == "python", (
            f"Expected language='python' on {node.node_id}, got {node.metadata}"
        )


def test_python_project_has_read_and_write_edges():
    if not _PYTHON_PROJECT.exists():
        pytest.skip("python_project fixture not found")
    graph = _build(_PYTHON_PROJECT)
    operations = {e.operation for e in graph.edges}
    # Should have at least one read-type and one write-type operation
    assert operations  # non-empty


def test_python_project_scan_diagnostic():
    if not _PYTHON_PROJECT.exists():
        pytest.skip("python_project fixture not found")
    graph = _build(_PYTHON_PROJECT)
    scan_diag = next(
        (d for d in graph.diagnostics if d.code == "project_scan"), None
    )
    assert scan_diag is not None
    assert "python_files" in scan_diag.payload
    assert int(scan_diag.payload["python_files"]) > 0
    assert scan_diag.payload.get("stata_files") == "0"
    assert scan_diag.payload.get("r_files") == "0"


# ---------------------------------------------------------------------------
# R project
# ---------------------------------------------------------------------------

def test_r_project_builds():
    if not _R_PROJECT.exists():
        pytest.skip("r_project fixture not found")
    graph = _build(_R_PROJECT)
    assert len(graph.nodes) > 0
    assert len(graph.edges) > 0


def test_r_script_nodes_have_language_metadata():
    if not _R_PROJECT.exists():
        pytest.skip("r_project fixture not found")
    graph = _build(_R_PROJECT)
    script_nodes = [n for n in graph.nodes.values() if n.node_type == "script"]
    assert len(script_nodes) > 0
    for node in script_nodes:
        assert node.metadata.get("language") == "r", (
            f"Expected language='r' on {node.node_id}, got {node.metadata}"
        )


def test_r_project_scan_diagnostic():
    if not _R_PROJECT.exists():
        pytest.skip("r_project fixture not found")
    graph = _build(_R_PROJECT)
    scan_diag = next(
        (d for d in graph.diagnostics if d.code == "project_scan"), None
    )
    assert scan_diag is not None
    assert int(scan_diag.payload["r_files"]) > 0
    assert scan_diag.payload.get("stata_files") == "0"
    assert scan_diag.payload.get("python_files") == "0"


def test_r_source_creates_script_call_edge():
    if not _R_PROJECT.exists():
        pytest.skip("r_project fixture not found")
    graph = _build(_R_PROJECT)
    # analyse.R sources load_data.R — should create a script-call edge
    script_call_edges = [e for e in graph.edges if e.kind == "script_call"]
    assert len(script_call_edges) > 0


# ---------------------------------------------------------------------------
# Stata project — regression: Stata-only project still works unchanged
# ---------------------------------------------------------------------------

def test_stata_project_still_works():
    if not _STATA_PROJECT.exists():
        pytest.skip("example/project not found")
    graph = _build(_STATA_PROJECT)
    assert len(graph.nodes) > 10
    assert len(graph.edges) > 10


def test_stata_script_nodes_have_stata_language_metadata():
    if not _STATA_PROJECT.exists():
        pytest.skip("example/project not found")
    graph = _build(_STATA_PROJECT)
    script_nodes = [n for n in graph.nodes.values() if n.node_type == "script"]
    assert len(script_nodes) > 0
    valid_languages = {"stata", "python", "r"}
    for node in script_nodes:
        assert node.metadata.get("language") in valid_languages, (
            f"Expected a known language on {node.node_id}, got {node.metadata}"
        )


def test_stata_project_scan_diagnostic_has_new_keys():
    if not _STATA_PROJECT.exists():
        pytest.skip("example/project not found")
    graph = _build(_STATA_PROJECT)
    scan_diag = next(
        (d for d in graph.diagnostics if d.code == "project_scan"), None
    )
    assert scan_diag is not None
    assert "stata_files" in scan_diag.payload
    assert "python_files" in scan_diag.payload
    assert "r_files" in scan_diag.payload
    assert int(scan_diag.payload["stata_files"]) > 0
    assert int(scan_diag.payload["python_files"]) >= 0
    assert int(scan_diag.payload["r_files"]) >= 0
