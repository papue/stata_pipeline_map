"""Tests for four dot-rendering bug fixes (phase 18).

Bug 1 — show_terminal_outputs=False hides leaf artifact nodes.
Bug 2 — edge_label_mode='operation' shows only the operation type, not the full visible_label.
Bug 3 — view='technical' uses raw node IDs and always shows edge labels.
Bug 4 — self-loop edges (source == target) are emitted, not silently dropped.
"""
from __future__ import annotations

from pathlib import Path

from stata_pipeline_flow.config.schema import AppConfig, DisplayConfig
from stata_pipeline_flow.model.entities import Edge, GraphModel, Node
from stata_pipeline_flow.render.dot import render_dot
from stata_pipeline_flow.rules.pipeline import PipelineBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _minimal_graph(project_root: Path) -> GraphModel:
    """One script that exports one CSV (deliverable, terminal output — never read by any other script)."""
    _write(project_root / "01_build.do", 'export delimited using "output.csv"\n')
    config = AppConfig(project_root=str(project_root))
    return PipelineBuilder(config).build(project_root)


# ---------------------------------------------------------------------------
# Bug 1 — show_terminal_outputs
# ---------------------------------------------------------------------------

def test_show_terminal_outputs_true_includes_leaf_artifact(tmp_path: Path) -> None:
    """Default (True): terminal output nodes appear in DOT."""
    graph = _minimal_graph(tmp_path)
    display = DisplayConfig(show_terminal_outputs=True)
    dot = render_dot(graph, display=display)
    assert "output.csv" in dot


def test_show_terminal_outputs_false_hides_leaf_artifact(tmp_path: Path) -> None:
    """show_terminal_outputs=False: leaf artifact nodes are excluded from DOT."""
    graph = _minimal_graph(tmp_path)
    display = DisplayConfig(show_terminal_outputs=False)
    dot = render_dot(graph, display=display)
    # The script node must still be present.
    assert "01_build.do" in dot
    # The terminal output artifact must be absent.
    assert "output.csv" not in dot


def test_show_terminal_outputs_false_only_hides_true_leaf_nodes(tmp_path: Path) -> None:
    """An artifact that feeds another script is NOT a terminal output and must remain."""
    # panel.dta is written by 01_build.do and read by 02_analyze.do — it has an
    # outgoing edge so it is NOT a terminal output and must stay visible.
    # results.csv is only written and never read — it IS a terminal output.
    _write(tmp_path / "01_build.do", 'save "panel.dta", replace\n')
    _write(tmp_path / "02_analyze.do", 'use "panel.dta", clear\nexport delimited using "results.csv"\n')
    config = AppConfig(project_root=str(tmp_path))
    graph = PipelineBuilder(config).build(tmp_path)

    display = DisplayConfig(show_terminal_outputs=False)
    dot = render_dot(graph, display=display)

    # panel.dta is consumed by 02_analyze.do → not a terminal output → must appear.
    assert "panel.dta" in dot
    # results.csv is a terminal output (nothing reads it) → must be hidden.
    assert "results.csv" not in dot


# ---------------------------------------------------------------------------
# Bug 2 — edge_label_mode: operation
# ---------------------------------------------------------------------------

def test_edge_label_mode_show_includes_full_visible_label() -> None:
    """edge_label_mode='show' renders the full visible_label on edges."""
    graph = GraphModel(project_root="/fake")
    graph.nodes["script.do"] = Node(node_id="script.do", label="script.do", node_type="script")
    graph.nodes["out.csv"] = Node(node_id="out.csv", label="out.csv", node_type="artifact")
    graph.edges.append(
        Edge(
            source="script.do",
            target="out.csv",
            operation="export",
            kind="write",
            visible_label="export delimited",
        )
    )

    display = DisplayConfig(edge_label_mode="show")
    dot = render_dot(graph, display=display)
    assert "export delimited" in dot


def test_edge_label_mode_operation_shows_only_operation_type(tmp_path: Path) -> None:
    """edge_label_mode='operation' shows only the operation field, not the full visible_label."""
    # Build a graph with a known edge by direct model construction.
    graph = GraphModel(project_root="/fake")
    graph.nodes["script.do"] = Node(node_id="script.do", label="script.do", node_type="script")
    graph.nodes["out.dta"] = Node(node_id="out.dta", label="out.dta", node_type="artifact")
    # Edge with a verbose visible_label but a short operation.
    graph.edges.append(
        Edge(
            source="script.do",
            target="out.dta",
            operation="save",
            kind="write",
            visible_label="save (replace)",
        )
    )

    display_op = DisplayConfig(edge_label_mode="operation")
    dot_op = render_dot(graph, display=display_op)

    display_show = DisplayConfig(edge_label_mode="show")
    dot_show = render_dot(graph, display=display_show)

    # 'operation' mode must include the operation field value.
    assert 'label="save"' in dot_op
    # 'operation' mode must NOT include the full verbose label.
    assert "save (replace)" not in dot_op
    # 'show' mode includes the full verbose label.
    assert "save (replace)" in dot_show


def test_edge_label_mode_hidden_suppresses_labels(tmp_path: Path) -> None:
    """edge_label_mode='hidden' suppresses all edge labels."""
    _write(tmp_path / "01_build.do", 'save "panel.dta", replace\n')
    config = AppConfig(project_root=str(tmp_path))
    graph = PipelineBuilder(config).build(tmp_path)

    display = DisplayConfig(edge_label_mode="hidden")
    dot = render_dot(graph, display=display)
    assert 'label=' not in dot or all(
        'label=' not in line for line in dot.splitlines() if "->" in line
    )


# ---------------------------------------------------------------------------
# Bug 3 — technical view
# ---------------------------------------------------------------------------

def test_technical_view_uses_raw_node_ids_as_labels(tmp_path: Path) -> None:
    """view='technical' renders raw node IDs rather than display names."""
    _write(tmp_path / "01_data/02_scripts/01_build.do", 'save "01_data/03_cleaned/panel.dta", replace\n')
    config = AppConfig(project_root=str(tmp_path))
    graph = PipelineBuilder(config).build(tmp_path)

    display_tech = DisplayConfig(view="technical")
    dot_tech = render_dot(graph, display=display_tech)

    display_overview = DisplayConfig(view="overview")
    dot_overview = render_dot(graph, display=display_overview)

    # In technical view the full relative path should appear as the label.
    assert 'label="01_data/02_scripts/01_build.do"' in dot_tech
    # In overview view only the basename is shown (label_path_depth=0 default).
    assert 'label="01_build.do"' in dot_overview
    # The full path label must NOT be present in overview.
    assert 'label="01_data/02_scripts/01_build.do"' not in dot_overview


def test_technical_view_shows_edge_labels_regardless_of_label_mode(tmp_path: Path) -> None:
    """view='technical' forces edge labels on even when edge_label_mode='hidden'."""
    _write(tmp_path / "01_build.do", 'save "panel.dta", replace\n')
    config = AppConfig(project_root=str(tmp_path))
    graph = PipelineBuilder(config).build(tmp_path)

    # hidden label mode combined with technical view → labels should still appear.
    display = DisplayConfig(view="technical", edge_label_mode="hidden")
    dot = render_dot(graph, display=display)

    # At least one edge label must be present.
    assert "label=" in dot


def test_technical_view_differs_from_overview(tmp_path: Path) -> None:
    """technical view must produce different DOT output than overview."""
    _write(tmp_path / "01_data/02_scripts/01_build.do", 'save "01_data/03_cleaned/panel.dta", replace\n')
    config = AppConfig(project_root=str(tmp_path))
    graph = PipelineBuilder(config).build(tmp_path)

    dot_tech = render_dot(graph, display=DisplayConfig(view="technical"))
    dot_overview = render_dot(graph, display=DisplayConfig(view="overview"))

    assert dot_tech != dot_overview


# ---------------------------------------------------------------------------
# Bug 4 — self-loop edges
# ---------------------------------------------------------------------------

def test_self_loop_edge_is_emitted_in_dot() -> None:
    """Edges where source == target must appear in DOT output (not silently dropped)."""
    graph = GraphModel(project_root="/fake")
    graph.nodes["script.do"] = Node(node_id="script.do", label="script.do", node_type="script")
    # Self-loop: script reads and rewrites the same artifact indirectly represented
    # as a same-node edge.
    graph.edges.append(
        Edge(
            source="script.do",
            target="script.do",
            operation="self",
            kind="self",
        )
    )

    dot = render_dot(graph)
    assert '"script.do" -> "script.do"' in dot


def test_self_loop_edge_with_label_is_emitted() -> None:
    """Self-loop with a visible_label renders with the label attribute."""
    graph = GraphModel(project_root="/fake")
    graph.nodes["n"] = Node(node_id="n", label="n", node_type="artifact")
    graph.edges.append(
        Edge(source="n", target="n", operation="loop", kind="self", visible_label="recur")
    )

    display = DisplayConfig(edge_label_mode="show")
    dot = render_dot(graph, display=display)
    assert '"n" -> "n"' in dot
    assert 'label="recur"' in dot


def test_self_loop_does_not_suppress_other_edges() -> None:
    """Presence of a self-loop must not prevent normal edges from being rendered."""
    graph = GraphModel(project_root="/fake")
    graph.nodes["a"] = Node(node_id="a", label="a", node_type="script")
    graph.nodes["b"] = Node(node_id="b", label="b", node_type="artifact")
    graph.edges.append(Edge(source="a", target="b", operation="save", kind="write"))
    graph.edges.append(Edge(source="a", target="a", operation="self", kind="self"))

    dot = render_dot(graph)
    assert '"a" -> "b"' in dot
    assert '"a" -> "a"' in dot
