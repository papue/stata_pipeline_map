"""
Category 4.2 stress test: Silent Data Loss Chain (parser -> multi_extract allowlist).

Demonstrates that when a parser emits a command label NOT in the allowlist,
the event is silently dropped with no diagnostic or warning.

Key finding: The current Python and R allowlists are COMPLETE -- no labels
emitted by the parsers are missing. However, the routing code at
multi_extract.py lines 249-265 has NO safety net: if a future parser change
introduces a new label without updating the allowlist, the event will be
silently discarded. This test proves the mechanism by monkeypatching.
"""
from __future__ import annotations

import pytest
from pathlib import Path

from data_pipeline_flow.parser import multi_extract
from data_pipeline_flow.parser.python_extract import parse_python_file
from data_pipeline_flow.config.schema import (
    ClassificationConfig,
    DisplayConfig,
    ExclusionConfig,
    NormalizationConfig,
    ParserConfig,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "stress" / "silent_drop_test"


def _default_configs():
    return (
        ExclusionConfig(),
        ParserConfig(),
        NormalizationConfig(),
        ClassificationConfig(),
        DisplayConfig(),
    )


def test_parser_emits_expected_commands():
    """Verify the parser emits events for the fixture file."""
    exclusions, parser, normalization, _, _ = _default_configs()
    result = parse_python_file(
        project_root=FIXTURE_DIR,
        py_file=FIXTURE_DIR / "read_yaml.py",
        exclusions=exclusions,
        normalization=normalization,
        parser_config=parser,
    )
    commands = [e.command for e in result.events]
    # open_read matches yaml.safe_load(open(...)) before yaml_safe_load
    # read_csv matches pd.read_csv(...)
    assert "open_read" in commands
    assert "read_csv" in commands


def test_baseline_edges_exist():
    """Baseline: both open_read and read_csv are in _PYTHON_READ_CMDS -> edges appear."""
    exclusions, parser, normalization, classification, display = _default_configs()
    graph = multi_extract.build_graph_from_scripts(
        project_root=FIXTURE_DIR,
        script_files=["read_yaml.py"],
        exclusions=exclusions,
        parser_config=parser,
        normalization=normalization,
        classification_config=classification,
        display_config=display,
    )
    ops = [e.operation for e in graph.edges]
    assert "open_read" in ops, f"open_read should be routed. All ops: {ops}"
    assert "read_csv" in ops, f"read_csv should be routed. All ops: {ops}"


def test_silent_drop_when_label_removed_from_allowlist():
    """
    Remove read_csv from the allowlist -> the read_csv event is silently dropped.
    No edge is created and NO diagnostic is emitted about the drop.
    This proves the silent data loss mechanism.
    """
    exclusions, parser, normalization, classification, display = _default_configs()

    original = multi_extract._PYTHON_READ_CMDS.copy()
    multi_extract._PYTHON_READ_CMDS.discard("read_csv")
    try:
        graph = multi_extract.build_graph_from_scripts(
            project_root=FIXTURE_DIR,
            script_files=["read_yaml.py"],
            exclusions=exclusions,
            parser_config=parser,
            normalization=normalization,
            classification_config=classification,
            display_config=display,
        )
        # read_csv edge should be gone
        csv_edges = [e for e in graph.edges if e.operation == "read_csv"]
        assert len(csv_edges) == 0, "read_csv edge should be dropped"

        # open_read edge should still be there
        open_edges = [e for e in graph.edges if e.operation == "open_read"]
        assert len(open_edges) == 1, "open_read should still be routed"

        # CRITICAL: No diagnostic about the silent drop
        drop_diags = [
            d for d in graph.diagnostics
            if any(kw in d.code for kw in ("not_routed", "label", "drop", "unrecognized"))
        ]
        assert len(drop_diags) == 0, (
            f"Confirmed: NO diagnostic for the silently dropped event. "
            f"The data.csv artifact vanishes without a trace."
        )

        # The data.csv artifact node should be gone too
        data_nodes = [n for n in graph.nodes.values() if "data.csv" in n.node_id]
        assert len(data_nodes) == 0, (
            "Confirmed: the artifact node for data.csv is also silently lost"
        )
    finally:
        multi_extract._PYTHON_READ_CMDS = original


def test_all_python_labels_in_allowlist():
    """
    Audit: every label the Python parser can emit must be in _PYTHON_READ_CMDS
    or _PYTHON_WRITE_CMDS. This test catches future drift.
    """
    from data_pipeline_flow.parser.python_extract import (
        _FIXED_READ_PATTERNS,
        _FIXED_WRITE_PATTERNS,
        _DEFAULT_PD_READ,
        _DEFAULT_NP_READ,
        _DEFAULT_WRITE_PATTERNS,
        _DEFAULT_PLT_WRITE,
        _DEFAULT_NP_WRITE,
        _make_gpd_read_patterns,
    )

    # Collect all possible labels from the parser
    emitted_read_labels = set()
    for cmd, _ in _DEFAULT_PD_READ + _DEFAULT_NP_READ + _FIXED_READ_PATTERNS:
        emitted_read_labels.add(cmd)
    for cmd, _ in _make_gpd_read_patterns(["gpd", "geopandas"]):
        emitted_read_labels.add(cmd)
    # runpy is emitted directly in the main loop
    emitted_read_labels.add("runpy")

    emitted_write_labels = set()
    for cmd, _ in _DEFAULT_WRITE_PATTERNS + _DEFAULT_PLT_WRITE + _DEFAULT_NP_WRITE + _FIXED_WRITE_PATTERNS:
        emitted_write_labels.add(cmd)

    read_missing = emitted_read_labels - multi_extract._PYTHON_READ_CMDS
    write_missing = emitted_write_labels - multi_extract._PYTHON_WRITE_CMDS

    assert not read_missing, f"Python read labels NOT in allowlist (will be silently dropped): {read_missing}"
    assert not write_missing, f"Python write labels NOT in allowlist (will be silently dropped): {write_missing}"


def test_all_r_labels_in_allowlist():
    """
    Audit: every label the R parser can emit must be in _R_READ_CMDS
    or _R_WRITE_CMDS. This test catches future drift.
    """
    from data_pipeline_flow.parser.r_extract import (
        _READS_FIRST_ARG,
        _WRITES_DATA_THEN_PATH,
        _WRITES_KEYWORD,
    )

    emitted_read_labels = set()
    for cmd, _ in _READS_FIRST_ARG:
        emitted_read_labels.add(cmd)
    # readRDS from keyword form uses same label
    emitted_read_labels.add("readRDS")

    emitted_write_labels = set()
    for cmd, _ in _WRITES_DATA_THEN_PATH + _WRITES_KEYWORD:
        emitted_write_labels.add(cmd)

    read_missing = emitted_read_labels - multi_extract._R_READ_CMDS
    write_missing = emitted_write_labels - multi_extract._R_WRITE_CMDS

    assert not read_missing, f"R read labels NOT in allowlist (will be silently dropped): {read_missing}"
    assert not write_missing, f"R write labels NOT in allowlist (will be silently dropped): {write_missing}"
