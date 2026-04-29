"""
NH-06: os.walk wildcard read + open(variable, mode) double-emit fix.

Verifies:
  - os.walk(FOLDER) emits a wildcard read edge FOLDER/**/*.{suffix}
  - open("path", "w")  does NOT emit an open_read event (spurious read fixed)
  - open("path", "r")  DOES emit an open_read event (explicit read mode)
  - open("path")       DOES emit an open_read event (default mode = read)
  - The oswalk_openvariable fixture produces exactly 2 edges: os_walk read + open_write,
    with no cycle diagnostic.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from data_pipeline_flow.config.schema import AppConfig
from data_pipeline_flow.parser.python_extract import parse_python_file

FIXTURES = Path(__file__).parent / "fixtures" / "oswalk_openvariable" / "analysis"
PROJECT_ROOT = Path(__file__).parent / "fixtures" / "oswalk_openvariable"


def _parse(filename: str):
    cfg = AppConfig()
    return parse_python_file(
        project_root=PROJECT_ROOT,
        py_file=FIXTURES / filename,
        exclusions=cfg.exclusions,
        normalization=cfg.normalization,
        parser_config=cfg.parser,
    )


def _parse_source(source: str):
    """Parse an in-memory Python snippet using a temp file path under the fixture root."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.py', dir=FIXTURES, delete=False, encoding='utf-8'
    ) as f:
        f.write(source)
        tmp = Path(f.name)
    try:
        cfg = AppConfig()
        return parse_python_file(
            project_root=PROJECT_ROOT,
            py_file=tmp,
            exclusions=cfg.exclusions,
            normalization=cfg.normalization,
            parser_config=cfg.parser,
        )
    finally:
        os.unlink(tmp)


def _read_paths(result) -> list[str]:
    return [
        norm
        for ev in result.events
        for norm in ev.normalized_paths
        if not ev.is_write
    ]


def _write_paths(result) -> list[str]:
    return [
        norm
        for ev in result.events
        for norm in ev.normalized_paths
        if ev.is_write
    ]


def _commands(result) -> set[str]:
    return {ev.command for ev in result.events}


# ---------------------------------------------------------------------------
# Fix 1 — os.walk wildcard read
# ---------------------------------------------------------------------------

def test_oswalk_emits_wildcard_pkl_read():
    """os.walk(BASE_DIR) with files.endswith('.pkl') filter should emit a
    wildcard read edge ending with **/*.pkl."""
    result = _parse("check_completeness.py")
    reads = _read_paths(result)
    assert any("**/*.pkl" in p or "**\\*.pkl" in p for p in reads), (
        f"Expected wildcard **/*.pkl read edge from os.walk, got: {reads}"
    )


def test_oswalk_command_label():
    """The os.walk event should have command='os_walk'."""
    result = _parse("check_completeness.py")
    assert 'os_walk' in _commands(result), (
        f"Expected 'os_walk' command in events, got: {_commands(result)}"
    )


def test_oswalk_without_suffix_emits_star_glob():
    """os.walk(FOLDER) with no suffix filter emits FOLDER/**/*."""
    src = (
        "import os\n"
        "BASE = 'data'\n"
        "for root, dirs, files in os.walk(BASE):\n"
        "    pass\n"
    )
    result = _parse_source(src)
    reads = _read_paths(result)
    assert any(p.endswith("/**/*") or p.endswith("**/*") for p in reads), (
        f"Expected /**/* wildcard from os.walk without suffix filter, got: {reads}"
    )


# ---------------------------------------------------------------------------
# Fix 2 — open_read regex: mode-gated (no spurious read on write mode)
# ---------------------------------------------------------------------------

def test_open_write_mode_does_not_emit_open_read():
    """open('path', 'w') must NOT emit an open_read event."""
    src = "f = open('output.txt', 'w')\n"
    result = _parse_source(src)
    assert 'open_read' not in _commands(result), (
        f"open('path', 'w') should not emit open_read, commands={_commands(result)}"
    )


def test_open_write_bytes_mode_does_not_emit_open_read():
    """open('path', 'wb') must NOT emit an open_read event."""
    src = "f = open('output.bin', 'wb')\n"
    result = _parse_source(src)
    assert 'open_read' not in _commands(result), (
        f"open('path', 'wb') should not emit open_read, commands={_commands(result)}"
    )


def test_open_append_mode_does_not_emit_open_read():
    """open('path', 'a') must NOT emit an open_read event."""
    src = "f = open('log.txt', 'a')\n"
    result = _parse_source(src)
    assert 'open_read' not in _commands(result), (
        f"open('path', 'a') should not emit open_read, commands={_commands(result)}"
    )


def test_open_default_mode_emits_open_read():
    """open('path') with no mode defaults to read and MUST emit open_read."""
    src = "f = open('data/input.txt')\n"
    result = _parse_source(src)
    assert 'open_read' in _commands(result), (
        f"open('path') should emit open_read, commands={_commands(result)}"
    )


def test_open_explicit_r_mode_emits_open_read():
    """open('path', 'r') must emit open_read."""
    src = "f = open('data/input.txt', 'r')\n"
    result = _parse_source(src)
    assert 'open_read' in _commands(result), (
        f"open('path', 'r') should emit open_read, commands={_commands(result)}"
    )


def test_open_rb_mode_emits_open_read():
    """open('path', 'rb') must emit open_read."""
    src = "f = open('data/input.bin', 'rb')\n"
    result = _parse_source(src)
    assert 'open_read' in _commands(result), (
        f"open('path', 'rb') should emit open_read, commands={_commands(result)}"
    )


# ---------------------------------------------------------------------------
# Integration: no cycle in the fixture
# ---------------------------------------------------------------------------

def test_no_cycle_in_oswalk_fixture():
    """After the fixes, the oswalk_openvariable fixture must produce no cycle diagnostic."""
    from data_pipeline_flow.parser.discovery import discover_project_files
    from data_pipeline_flow.parser.multi_extract import build_graph_from_scripts

    cfg = AppConfig()
    scan = discover_project_files(PROJECT_ROOT, cfg.exclusions, cfg.normalization, cfg.languages)
    graph = build_graph_from_scripts(
        project_root=PROJECT_ROOT,
        script_files=scan.script_files,
        exclusions=cfg.exclusions,
        parser_config=cfg.parser,
        normalization=cfg.normalization,
        classification_config=cfg.classification,
        display_config=cfg.display,
    )
    cycle_diags = [d for d in graph.diagnostics if d.code == 'cycle_detected']
    assert not cycle_diags, (
        f"Unexpected cycle diagnostics after NH-06 fix: {cycle_diags}"
    )


def test_oswalk_fixture_write_edge_present():
    """The fixture must have a write edge from check_completeness.py to completeness_report.txt."""
    from data_pipeline_flow.parser.discovery import discover_project_files
    from data_pipeline_flow.parser.multi_extract import build_graph_from_scripts

    cfg = AppConfig()
    scan = discover_project_files(PROJECT_ROOT, cfg.exclusions, cfg.normalization, cfg.languages)
    graph = build_graph_from_scripts(
        project_root=PROJECT_ROOT,
        script_files=scan.script_files,
        exclusions=cfg.exclusions,
        parser_config=cfg.parser,
        normalization=cfg.normalization,
        classification_config=cfg.classification,
        display_config=cfg.display,
    )
    write_edges = [
        e for e in graph.edges
        if 'check_completeness' in e.source and 'completeness_report' in e.target
    ]
    assert write_edges, (
        f"Expected write edge from check_completeness.py to completeness_report.txt, "
        f"edges: {[(e.source, e.target) for e in graph.edges]}"
    )


def test_oswalk_fixture_read_edge_present():
    """The fixture must have an os_walk read edge containing **/*.pkl."""
    from data_pipeline_flow.parser.discovery import discover_project_files
    from data_pipeline_flow.parser.multi_extract import build_graph_from_scripts

    cfg = AppConfig()
    scan = discover_project_files(PROJECT_ROOT, cfg.exclusions, cfg.normalization, cfg.languages)
    graph = build_graph_from_scripts(
        project_root=PROJECT_ROOT,
        script_files=scan.script_files,
        exclusions=cfg.exclusions,
        parser_config=cfg.parser,
        normalization=cfg.normalization,
        classification_config=cfg.classification,
        display_config=cfg.display,
    )
    read_edges = [
        e for e in graph.edges
        if ('**/*.pkl' in e.source or '**\\*.pkl' in e.source)
        and 'check_completeness' in e.target
    ]
    assert read_edges, (
        f"Expected os_walk read edge (wildcard **/*.pkl -> check_completeness.py), "
        f"edges: {[(e.source, e.target) for e in graph.edges]}"
    )
