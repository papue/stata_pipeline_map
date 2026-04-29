"""
NH-08: Deliverable classification regression tests.

Verifies that:
  - Data-format files consumed by another script are classified as `intermediate`
    (not `deliverable`) — both in node role and write-edge kind.
  - Data-format files with no downstream consumers retain `deliverable`.
  - Presentation-format files (.png, .pdf, etc.) remain `deliverable` regardless
    of consumer count.
  - The fix applies consistently across Python, Stata, and R fixtures.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from data_pipeline_flow.config.schema import AppConfig
from data_pipeline_flow.parser.discovery import discover_project_files
from data_pipeline_flow.parser.multi_extract import build_graph_from_scripts

FIXTURES = Path(__file__).parent / "fixtures" / "deliverable_classification"


def _build_graph(fixture_dir: Path):
    cfg = AppConfig()
    scan = discover_project_files(fixture_dir, cfg.exclusions, cfg.normalization, cfg.languages)
    return build_graph_from_scripts(
        project_root=fixture_dir,
        script_files=scan.script_files,
        exclusions=cfg.exclusions,
        parser_config=cfg.parser,
        normalization=cfg.normalization,
        classification_config=cfg.classification,
        display_config=cfg.display,
    )


def _node_role(graph, node_id: str) -> str | None:
    node = graph.nodes.get(node_id)
    return node.role if node else None


def _write_edge_kind(graph, target: str) -> str | None:
    """Return the kind of the write edge (script → target)."""
    for edge in graph.edges:
        if edge.target == target and edge.source != target:
            # write edges have source=script, target=artifact
            if not edge.target.endswith('.py') and not edge.target.endswith('.do') and not edge.target.endswith('.r'):
                return edge.kind
    return None


# ---------------------------------------------------------------------------
# Python fixture: intermediate-with-consumers
# ---------------------------------------------------------------------------

class TestPythonIntermediateWithConsumers:
    """Python fixture: parquet/csv/xlsx written by extract_data.py and consumed
    by generate_graphs.py — all three should be `intermediate`."""

    @pytest.fixture(scope="class")
    def graph(self):
        return _build_graph(FIXTURES / "analysis".parent)

    def setup_method(self):
        self._graph = _build_graph(FIXTURES)

    def test_parquet_node_role_is_intermediate(self):
        role = _node_role(self._graph, "analysis/results/all_results.parquet")
        # path may be relative to the fixture sub-dir
        role = role or _node_role(self._graph, "results/all_results.parquet")
        assert role == "intermediate", (
            f"Expected 'intermediate' for all_results.parquet, got {role!r}"
        )

    def test_csv_node_role_is_intermediate(self):
        role = (_node_role(self._graph, "analysis/results/summary.csv")
                or _node_role(self._graph, "results/summary.csv"))
        assert role == "intermediate", (
            f"Expected 'intermediate' for summary.csv, got {role!r}"
        )

    def test_xlsx_node_role_is_intermediate(self):
        role = (_node_role(self._graph, "analysis/results/summary.xlsx")
                or _node_role(self._graph, "results/summary.xlsx"))
        assert role == "intermediate", (
            f"Expected 'intermediate' for summary.xlsx, got {role!r}"
        )

    def test_write_edge_kind_matches_node_role(self):
        """Write-edge kind must equal node role (no deliverable/intermediate split)."""
        graph = self._graph
        for node_id, node in graph.nodes.items():
            if node.node_type != "artifact":
                continue
            write_edges = [e for e in graph.edges if e.target == node_id]
            for edge in write_edges:
                assert edge.kind == node.role, (
                    f"Edge kind {edge.kind!r} != node role {node.role!r} for {node_id}"
                )


# ---------------------------------------------------------------------------
# Python fixture: deliverable-no-consumers
# ---------------------------------------------------------------------------

class TestPythonDeliverableNoConsumers:
    """final_table.csv is written by final_report.py and consumed by nobody —
    should stay `deliverable`."""

    def setup_method(self):
        self._graph = _build_graph(FIXTURES)

    def test_final_table_csv_is_deliverable(self):
        role = (_node_role(self._graph, "analysis/output/final_table.csv")
                or _node_role(self._graph, "output/final_table.csv"))
        assert role == "deliverable", (
            f"Expected 'deliverable' for final_table.csv, got {role!r}"
        )


# ---------------------------------------------------------------------------
# Python fixture: presentation-format always-deliverable
# ---------------------------------------------------------------------------

class TestPresentationFormatAlwaysDeliverable:
    """plot.png is written by generate_graphs.py — presentation formats must
    remain `deliverable` regardless of consumer count."""

    def setup_method(self):
        self._graph = _build_graph(FIXTURES)

    def test_png_is_deliverable(self):
        role = (_node_role(self._graph, "analysis/output/plot.png")
                or _node_role(self._graph, "output/plot.png"))
        assert role == "deliverable", (
            f"Expected 'deliverable' for plot.png, got {role!r}"
        )


# ---------------------------------------------------------------------------
# Stata fixture: .dta consumed downstream → intermediate
# ---------------------------------------------------------------------------

class TestStataIntermediateDta:
    """Stata fixture: clean.dta written by writer.do and consumed by reader.do
    should be `intermediate`."""

    def setup_method(self):
        self._graph = _build_graph(FIXTURES / "stata_check")

    def test_clean_dta_is_intermediate(self):
        role = _node_role(self._graph, "data/processed/clean.dta")
        assert role == "intermediate", (
            f"Expected 'intermediate' for clean.dta, got {role!r}"
        )

    def test_survey_dta_is_reference_input(self):
        role = _node_role(self._graph, "data/raw/survey.dta")
        assert role == "reference_input", (
            f"Expected 'reference_input' for survey.dta, got {role!r}"
        )


# ---------------------------------------------------------------------------
# R fixture: .rds/.csv consumed downstream → intermediate
# ---------------------------------------------------------------------------

class TestRIntermediateRds:
    """R fixture: model.rds and output.csv written by writer.R and consumed by
    reader.R should both be `intermediate`."""

    def setup_method(self):
        self._graph = _build_graph(FIXTURES / "r_check")

    def test_rds_is_intermediate(self):
        role = _node_role(self._graph, "results/model.rds")
        assert role == "intermediate", (
            f"Expected 'intermediate' for model.rds, got {role!r}"
        )

    def test_csv_is_intermediate(self):
        role = _node_role(self._graph, "results/output.csv")
        assert role == "intermediate", (
            f"Expected 'intermediate' for output.csv, got {role!r}"
        )
