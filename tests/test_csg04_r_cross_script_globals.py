"""
CSG-04 — Cross-script global propagation: R fix.

Regression tests verifying that variables defined in a calling R script before
a source() call are inherited by the sourced child (and grandchild) scripts
during multi-script parsing.

Scenarios covered:
  1. Single-level inheritance: ROOT_DIR / OUTPUT_DIR from run_analysis.R
     resolve in analysis/plot_results.R and analysis/export_tables.R.
  2. Two-level (grandchild) inheritance: DATA_ROOT defined in main.R → STAGE_DIR
     built in pipeline/stage1.R → used in pipeline/stage1_process.R.
  3. No placeholder nodes remain after propagation.
  4. No partial-resolution diagnostics are emitted.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from data_pipeline_flow.config.schema import AppConfig
from data_pipeline_flow.parser.multi_extract import build_graph_from_scripts

FIXTURES = Path(__file__).parent / "fixtures"
CSG_R_FIXTURE = FIXTURES / "cross_script_globals_r"


def _build(project_root: Path) -> object:
    """Build a GraphModel for all .R files found under project_root."""
    cfg = AppConfig()
    r_files = sorted(
        str(p.relative_to(project_root)).replace("\\", "/")
        for p in project_root.rglob("*.R")
    )
    return build_graph_from_scripts(
        project_root=project_root,
        script_files=r_files,
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
# 1. Single-level inheritance
# ---------------------------------------------------------------------------

def _normalize_edge_set(edges: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Normalise edge endpoints to lowercase for case-insensitive comparison."""
    return {(s.lower(), t.lower()) for s, t in edges}


def test_single_level_r_var_inheritance_read_edge():
    """ROOT_DIR defined in run_analysis.R must resolve read_csv in sourced scripts."""
    graph = _build(CSG_R_FIXTURE)
    edges = _normalize_edge_set(_edge_set(graph))

    # Both child scripts read data/processed/estimates.csv (ROOT_DIR = "data/processed")
    assert ("data/processed/estimates.csv", "analysis/plot_results.r") in edges, (
        "Expected edge: data/processed/estimates.csv → analysis/plot_results.r"
    )
    assert ("data/processed/estimates.csv", "analysis/export_tables.r") in edges, (
        "Expected edge: data/processed/estimates.csv → analysis/export_tables.r"
    )


def test_single_level_r_var_inheritance_write_edge():
    """OUTPUT_DIR defined in run_analysis.R must resolve write paths in sourced scripts."""
    graph = _build(CSG_R_FIXTURE)
    edges = _normalize_edge_set(_edge_set(graph))

    # plot_results.R writes output/figures/estimates_plot.png (OUTPUT_DIR = "output/figures")
    assert ("analysis/plot_results.r", "output/figures/estimates_plot.png") in edges, (
        "Expected edge: analysis/plot_results.r → output/figures/estimates_plot.png"
    )
    # export_tables.R writes output/figures/estimates_table.csv
    assert ("analysis/export_tables.r", "output/figures/estimates_table.csv") in edges, (
        "Expected edge: analysis/export_tables.r → output/figures/estimates_table.csv"
    )


# ---------------------------------------------------------------------------
# 2. Two-level (grandchild) inheritance
# ---------------------------------------------------------------------------

def test_two_level_r_var_inheritance():
    """DATA_ROOT defined in main.R; STAGE_DIR built in stage1.R; used in stage1_process.R."""
    graph = _build(CSG_R_FIXTURE)
    edges = _normalize_edge_set(_edge_set(graph))

    # stage1_process.R reads data/stage1/input.csv (STAGE_DIR = "data/stage1")
    assert ("data/stage1/input.csv", "pipeline/stage1_process.r") in edges, (
        "Expected edge: data/stage1/input.csv → pipeline/stage1_process.r"
    )
    # stage1_process.R writes data/stage1/output.csv
    assert ("pipeline/stage1_process.r", "data/stage1/output.csv") in edges, (
        "Expected edge: pipeline/stage1_process.r → data/stage1/output.csv"
    )


# ---------------------------------------------------------------------------
# 3. No placeholder nodes after propagation
# ---------------------------------------------------------------------------

def test_no_placeholder_nodes_in_r_csg_fixture():
    """After fix, no artifact_placeholder nodes should remain in cross_script_globals_r."""
    graph = _build(CSG_R_FIXTURE)
    placeholders = _placeholder_nodes(graph)
    assert not placeholders, (
        f"Unexpected placeholder nodes after R variable propagation fix: {placeholders}"
    )


# ---------------------------------------------------------------------------
# 4. No partial-resolution diagnostics
# ---------------------------------------------------------------------------

def test_r_csg_fixture_no_partial_resolution_diagnostics():
    """No dynamic_path_partial_resolution diagnostics expected after the fix."""
    graph = _build(CSG_R_FIXTURE)
    partial = [
        d for d in graph.diagnostics
        if d.code == "dynamic_path_partial_resolution"
    ]
    assert not partial, (
        f"Unexpected partial-resolution diagnostics: "
        f"{[(d.payload.get('script'), d.payload.get('pattern')) for d in partial]}"
    )
