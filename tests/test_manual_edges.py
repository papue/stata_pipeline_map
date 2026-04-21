"""Tests for the manual_edges feature (Step 5).

Pattern: build minimal project in tmp_path, construct AppConfig,
call PipelineBuilder(config).build(project_root), assert on
graph.edges, graph.nodes, graph.diagnostics.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from stata_pipeline_flow.config.schema import (
    AppConfig,
    ManualClusterConfig,
    ManualEdgeConfig,
    _load_manual_edges,
    load_config,
)
from stata_pipeline_flow.rules.pipeline import PipelineBuilder


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write(path: Path, text: str = '* placeholder\n') -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _minimal_project(project_root: Path) -> None:
    """One script that saves one artifact — gives the parser something to find."""
    _write(
        project_root / 'scripts/01_build.do',
        'save "data/output.dta", replace\n',
    )


def _two_script_project(project_root: Path) -> None:
    """Two .do files with a shared artifact so both nodes end up in the graph."""
    _write(
        project_root / 'scripts/01_build.do',
        'save "data/panel.dta", replace\n',
    )
    _write(
        project_root / 'scripts/02_analysis.do',
        'use "data/panel.dta", clear\nsave "data/result.dta", replace\n',
    )


def _three_script_project(project_root: Path) -> None:
    """Three .do files producing a chain of artifacts; gives artifact→artifact pairs."""
    _write(
        project_root / 'scripts/01_build.do',
        'save "data/panel.dta", replace\n',
    )
    _write(
        project_root / 'scripts/02_prep.do',
        'use "data/panel.dta", clear\nsave "data/clean.dta", replace\n',
    )
    _write(
        project_root / 'scripts/03_export.do',
        'use "data/clean.dta", clear\nexport delimited using "data/output.csv"\n',
    )


def _diag(graph, code: str):
    """Return all diagnostics matching *code*."""
    return [d for d in graph.diagnostics if d.code == code]


def _manual_edge(graph):
    """Return all edges with operation='manual'."""
    return [e for e in graph.edges if e.operation == 'manual']


# ---------------------------------------------------------------------------
# Happy path / kind inference
# ---------------------------------------------------------------------------

def test_happy_path_both_nodes_exist(tmp_path: Path) -> None:
    """Both nodes exist → edge added with correct fields; summary applied=1 skipped=0."""
    project_root = tmp_path / 'proj'
    _two_script_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='scripts/02_analysis.do',
                label='feeds',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    manual = _manual_edge(graph)
    assert len(manual) == 1
    edge = manual[0]
    assert edge.source == 'scripts/01_build.do'
    assert edge.target == 'scripts/02_analysis.do'
    assert edge.operation == 'manual'
    assert edge.kind == 'script_to_script'
    assert edge.visible_label == 'feeds'

    summaries = _diag(graph, 'manual_edges_applied')
    assert len(summaries) == 1
    assert summaries[0].payload['applied'] == '1'
    assert summaries[0].payload['skipped'] == '0'
    assert summaries[0].payload['total'] == '1'


def test_kind_script_to_script(tmp_path: Path) -> None:
    """Two .do scripts → kind='script_to_script'."""
    project_root = tmp_path / 'proj'
    _two_script_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='scripts/02_analysis.do',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)
    assert _manual_edge(graph)[0].kind == 'script_to_script'


def test_kind_artifact_to_script(tmp_path: Path) -> None:
    """.dta artifact → .do script → kind='artifact_to_script'.

    Uses a pair with no existing parser edge between them so the manual edge is
    actually added (not flagged as a duplicate).
    """
    project_root = tmp_path / 'proj'
    _three_script_project(project_root)
    # data/output.csv → scripts/01_build.do has no parser edge
    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='data/output.csv',
                target='scripts/01_build.do',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)
    manual = _manual_edge(graph)
    assert len(manual) == 1
    assert manual[0].kind == 'artifact_to_script'


def test_kind_artifact_to_artifact(tmp_path: Path) -> None:
    """.csv → .dta → kind='artifact_to_artifact'.

    Uses two artifact nodes that already exist in the graph but have no parser edge
    directly between them, so the manual edge is added and not flagged as a duplicate.
    """
    project_root = tmp_path / 'proj'
    _three_script_project(project_root)
    # data/output.csv and data/panel.dta are both in the graph;
    # no parser edge connects them directly.
    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='data/output.csv',
                target='data/panel.dta',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)
    manual = _manual_edge(graph)
    assert len(manual) == 1
    assert manual[0].kind == 'artifact_to_artifact'


def test_no_label_gives_visible_label_none(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    _two_script_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='scripts/02_analysis.do',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)
    assert _manual_edge(graph)[0].visible_label is None


def test_note_field_not_in_edge_or_node(tmp_path: Path) -> None:
    """note field is accepted but produces no diagnostic and is not stored on edge or node."""
    project_root = tmp_path / 'proj'
    _two_script_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='scripts/02_analysis.do',
                note='Parser misses this because path is macro-resolved',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    manual = _manual_edge(graph)
    assert len(manual) == 1
    edge = manual[0]
    # Edge dataclass has no 'note' field
    assert not hasattr(edge, 'note')
    # No diagnostic specifically about the note
    note_diags = [d for d in graph.diagnostics if 'note' in d.code]
    assert note_diags == []


# ---------------------------------------------------------------------------
# Validation — blank fields
# ---------------------------------------------------------------------------

def test_blank_source_emits_invalid_manual_edge(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(source='', target='data/output.dta')
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    warnings = _diag(graph, 'invalid_manual_edge')
    assert len(warnings) == 1
    assert warnings[0].level == 'warning'
    assert _manual_edge(graph) == []

    summaries = _diag(graph, 'manual_edges_applied')
    assert summaries[0].payload['skipped'] == '1'
    assert summaries[0].payload['applied'] == '0'


def test_blank_target_emits_invalid_manual_edge(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(source='scripts/01_build.do', target='')
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    warnings = _diag(graph, 'invalid_manual_edge')
    assert len(warnings) == 1
    assert warnings[0].level == 'warning'
    assert _manual_edge(graph) == []


# ---------------------------------------------------------------------------
# Node-not-found / on_missing
# ---------------------------------------------------------------------------

def test_one_node_missing_warn_emits_node_not_found(tmp_path: Path) -> None:
    """Source exists, target missing → warning, edge skipped, no phantom node."""
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='data/does_not_exist.dta',
                on_missing='warn',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    not_found = _diag(graph, 'manual_edge_node_not_found')
    assert len(not_found) == 1
    assert not_found[0].level == 'warning'
    assert not_found[0].payload['node_id'] == 'data/does_not_exist.dta'
    assert _manual_edge(graph) == []
    assert 'data/does_not_exist.dta' not in graph.nodes


def test_both_nodes_missing_warn_emits_two_warnings(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='data/ghost_a.dta',
                target='data/ghost_b.dta',
                on_missing='warn',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    not_found = _diag(graph, 'manual_edge_node_not_found')
    assert len(not_found) == 2
    node_ids = {d.payload['node_id'] for d in not_found}
    assert node_ids == {'data/ghost_a.dta', 'data/ghost_b.dta'}
    assert _manual_edge(graph) == []


def test_one_node_missing_placeholder_injects_node_and_adds_edge(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='data/not_yet_present.dta',
                on_missing='placeholder',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    # Placeholder node injected
    assert 'data/not_yet_present.dta' in graph.nodes
    ph_node = graph.nodes['data/not_yet_present.dta']
    assert ph_node.node_type == 'artifact_placeholder'

    # Edge added
    manual = _manual_edge(graph)
    assert len(manual) == 1
    assert manual[0].target == 'data/not_yet_present.dta'

    # Info diagnostic emitted
    injected = _diag(graph, 'manual_edge_placeholder_injected')
    assert len(injected) == 1
    assert injected[0].level == 'info'
    assert injected[0].payload['node_id'] == 'data/not_yet_present.dta'


def test_both_nodes_missing_placeholder_injects_two_nodes_one_edge(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='data/ghost_a.dta',
                target='data/ghost_b.dta',
                on_missing='placeholder',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    assert 'data/ghost_a.dta' in graph.nodes
    assert 'data/ghost_b.dta' in graph.nodes
    assert graph.nodes['data/ghost_a.dta'].node_type == 'artifact_placeholder'
    assert graph.nodes['data/ghost_b.dta'].node_type == 'artifact_placeholder'

    assert len(_manual_edge(graph)) == 1

    injected = _diag(graph, 'manual_edge_placeholder_injected')
    assert len(injected) == 2
    node_ids = {d.payload['node_id'] for d in injected}
    assert node_ids == {'data/ghost_a.dta', 'data/ghost_b.dta'}


def test_existing_parser_placeholder_plus_on_missing_placeholder_is_noop(tmp_path: Path) -> None:
    """If a node is already in the graph (injected as placeholder by an earlier manual entry),
    add_node on the second entry is a no-op: the node keeps its original type, edge is still
    added, and no second placeholder_injected diagnostic is emitted for that node.
    """
    project_root = tmp_path / 'proj'
    # _two_script_project gives us data/panel.dta in the graph as a real artifact.
    _two_script_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            # First entry: target 'data/ghost.dta' is missing → placeholder injected
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='data/ghost.dta',
                on_missing='placeholder',
            ),
            # Second entry: same target 'data/ghost.dta' — now already in graph.
            # Source 'data/panel.dta' is a real node, so no placeholder for it.
            # add_node for 'data/ghost.dta' must be a no-op (setdefault).
            ManualEdgeConfig(
                source='data/panel.dta',
                target='data/ghost.dta',
                on_missing='placeholder',
            ),
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    # Node should appear exactly once and keep artifact_placeholder type
    assert list(k for k in graph.nodes if k == 'data/ghost.dta') == ['data/ghost.dta']
    assert graph.nodes['data/ghost.dta'].node_type == 'artifact_placeholder'

    # Two manual edges added: 01_build.do→ghost and panel.dta→ghost
    manual = _manual_edge(graph)
    assert len(manual) == 2

    # Only one placeholder_injected diagnostic: for the first entry only
    injected = _diag(graph, 'manual_edge_placeholder_injected')
    assert len(injected) == 1
    assert injected[0].payload['node_id'] == 'data/ghost.dta'


# ---------------------------------------------------------------------------
# Duplicates
# ---------------------------------------------------------------------------

def test_parser_edge_then_same_manual_pair_emits_duplicate(tmp_path: Path) -> None:
    """Parser already created an edge; manual entry for same pair → manual_edge_duplicate info."""
    project_root = tmp_path / 'proj'
    # _two_script_project gives: parser edges 01_build.do→panel.dta and panel.dta→02_analysis.do
    _two_script_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            # Exactly matches the parser-created save edge
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='data/panel.dta',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    dup_diags = _diag(graph, 'manual_edge_duplicate')
    assert len(dup_diags) == 1
    assert dup_diags[0].level == 'info'
    assert dup_diags[0].payload['source'] == 'scripts/01_build.do'
    assert dup_diags[0].payload['target'] == 'data/panel.dta'

    # No extra manual edge added
    assert _manual_edge(graph) == []


def test_two_identical_manual_entries_second_gets_duplicate(tmp_path: Path) -> None:
    project_root = tmp_path / 'proj'
    _two_script_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='scripts/02_analysis.do',
            ),
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='scripts/02_analysis.do',
            ),
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    dup_diags = _diag(graph, 'manual_edge_duplicate')
    assert len(dup_diags) == 1

    # Only one manual edge in the graph
    manual = _manual_edge(graph)
    assert len(manual) == 1

    summary = _diag(graph, 'manual_edges_applied')[0]
    assert summary.payload['applied'] == '1'
    assert summary.payload['skipped'] == '1'
    assert summary.payload['total'] == '2'


# ---------------------------------------------------------------------------
# Summary diagnostics
# ---------------------------------------------------------------------------

def test_mix_valid_and_invalid_correct_summary(tmp_path: Path) -> None:
    """3 entries: 1 valid, 1 blank-source, 1 node-not-found → applied=1, skipped=2, total=3."""
    project_root = tmp_path / 'proj'
    _two_script_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='scripts/02_analysis.do',
            ),
            ManualEdgeConfig(source='', target='data/panel.dta'),
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='data/no_such_file.dta',
                on_missing='warn',
            ),
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    summary = _diag(graph, 'manual_edges_applied')[0]
    assert summary.payload['applied'] == '1'
    assert summary.payload['skipped'] == '2'
    assert summary.payload['total'] == '3'


def test_empty_manual_edges_no_applied_diagnostic(tmp_path: Path) -> None:
    """Empty manual_edges list → early return, no manual_edges_applied diagnostic."""
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[],
    )
    graph = PipelineBuilder(config).build(project_root)

    assert _diag(graph, 'manual_edges_applied') == []


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def test_load_config_valid_yaml_with_manual_edges(tmp_path: Path) -> None:
    """Valid YAML with manual_edges block → correct ManualEdgeConfig objects."""
    yaml_text = (
        'manual_edges:\n'
        '  - source: scripts/01_build.do\n'
        '    target: data/output.csv\n'
        '    label: "builds"\n'
        '    note: "Parser misses this"\n'
        '  - source: data/output.csv\n'
        '    target: scripts/02_analysis.do\n'
        '    on_missing: placeholder\n'
    )
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(yaml_text, encoding='utf-8')

    config = load_config(config_path)

    assert len(config.manual_edges) == 2
    e0 = config.manual_edges[0]
    assert e0.source == 'scripts/01_build.do'
    assert e0.target == 'data/output.csv'
    assert e0.label == 'builds'
    assert e0.note == 'Parser misses this'
    assert e0.on_missing == 'warn'

    e1 = config.manual_edges[1]
    assert e1.source == 'data/output.csv'
    assert e1.target == 'scripts/02_analysis.do'
    assert e1.on_missing == 'placeholder'


def test_load_manual_edges_on_missing_bad_value_falls_back_to_warn() -> None:
    """on_missing with unrecognised value coerces to 'warn' without raising."""
    raw = [{'source': 'a.do', 'target': 'b.dta', 'on_missing': 'explode'}]
    edges = _load_manual_edges(raw)
    assert len(edges) == 1
    assert edges[0].on_missing == 'warn'


def test_load_manual_edges_not_a_list_raises_value_error() -> None:
    with pytest.raises(ValueError, match='must be a list'):
        _load_manual_edges('not a list')


def test_load_config_on_missing_bad_value_via_yaml(tmp_path: Path) -> None:
    """Same coercion test but exercised through the full load_config path."""
    yaml_text = (
        'manual_edges:\n'
        '  - source: a.do\n'
        '    target: b.dta\n'
        '    on_missing: badvalue\n'
    )
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(yaml_text, encoding='utf-8')

    config = load_config(config_path)
    assert config.manual_edges[0].on_missing == 'warn'


def test_load_config_manual_edges_not_list_raises(tmp_path: Path) -> None:
    yaml_text = 'manual_edges: "not a list"\n'
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(yaml_text, encoding='utf-8')

    with pytest.raises(ValueError):
        load_config(config_path)


# ---------------------------------------------------------------------------
# Integration
# ---------------------------------------------------------------------------

def test_manual_edge_crosses_cluster_boundary(tmp_path: Path) -> None:
    """Manual edge between nodes in different clusters → edge present, clusters unchanged."""
    project_root = tmp_path / 'proj'
    _two_script_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        clusters=[
            ManualClusterConfig(
                cluster_id='build_stage',
                members=['scripts/01_build.do'],
            ),
            ManualClusterConfig(
                cluster_id='analysis_stage',
                members=['scripts/02_analysis.do'],
            ),
        ],
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='scripts/02_analysis.do',
                label='cross-cluster',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    manual = _manual_edge(graph)
    assert len(manual) == 1
    assert manual[0].visible_label == 'cross-cluster'

    # Cluster assignments are unchanged by the manual edge rule
    assert graph.nodes['scripts/01_build.do'].cluster_id == 'build_stage'
    assert graph.nodes['scripts/02_analysis.do'].cluster_id == 'analysis_stage'


# ---------------------------------------------------------------------------
# Extension-based placeholder type detection
# ---------------------------------------------------------------------------

def test_placeholder_script_extension_do_gets_script_placeholder(tmp_path: Path) -> None:
    """A missing node with a .do extension → node_type='script_placeholder'."""
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='scripts/missing_step.do',
                on_missing='placeholder',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    assert 'scripts/missing_step.do' in graph.nodes
    ph = graph.nodes['scripts/missing_step.do']
    assert ph.node_type == 'script_placeholder'
    assert ph.role == 'placeholder_script'

    manual = _manual_edge(graph)
    assert len(manual) == 1
    assert manual[0].kind == 'script_to_script'


def test_placeholder_script_extension_py_gets_script_placeholder(tmp_path: Path) -> None:
    """A missing node with a .py extension → node_type='script_placeholder'."""
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='04_python_prep/clean.py',
                on_missing='placeholder',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    assert '04_python_prep/clean.py' in graph.nodes
    ph = graph.nodes['04_python_prep/clean.py']
    assert ph.node_type == 'script_placeholder'
    assert ph.role == 'placeholder_script'

    manual = _manual_edge(graph)
    assert len(manual) == 1
    assert manual[0].kind == 'script_to_script'


def test_placeholder_script_extension_r_gets_script_placeholder(tmp_path: Path) -> None:
    """A missing node with a .R extension → node_type='script_placeholder'."""
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='05_r_analysis/model.R',
                on_missing='placeholder',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    ph = graph.nodes['05_r_analysis/model.R']
    assert ph.node_type == 'script_placeholder'


def test_placeholder_artifact_extension_dta_stays_artifact_placeholder(tmp_path: Path) -> None:
    """.dta extension → node_type='artifact_placeholder' (unchanged behavior)."""
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='data/missing_data.dta',
                on_missing='placeholder',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    ph = graph.nodes['data/missing_data.dta']
    assert ph.node_type == 'artifact_placeholder'
    assert ph.role == 'placeholder_artifact'


def test_placeholder_no_extension_defaults_to_artifact_placeholder(tmp_path: Path) -> None:
    """A missing node with no extension → node_type='artifact_placeholder'."""
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='data/no_extension_file',
                on_missing='placeholder',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    ph = graph.nodes['data/no_extension_file']
    assert ph.node_type == 'artifact_placeholder'
    assert ph.role == 'placeholder_artifact'


def test_placeholder_script_source_and_artifact_target_edge_kind(tmp_path: Path) -> None:
    """script_placeholder source + artifact target → edge kind='script_to_artifact'."""
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='04_python_prep/clean.py',
                target='data/output.dta',
                on_missing='placeholder',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    manual = _manual_edge(graph)
    assert len(manual) == 1
    # clean.py → script_placeholder; output.dta → artifact_placeholder
    assert manual[0].kind == 'script_to_artifact'


def test_no_manual_edges_key_in_yaml_pipeline_runs_normally(tmp_path: Path) -> None:
    """YAML without manual_edges key → AppConfig.manual_edges=[], pipeline runs fine."""
    project_root = tmp_path / 'proj'
    _minimal_project(project_root)

    yaml_text = 'project_root: .\n'
    config_path = project_root / 'config.yaml'
    config_path.write_text(yaml_text, encoding='utf-8')

    config = load_config(config_path)
    assert config.manual_edges == []

    graph = PipelineBuilder(config).build(project_root)
    assert _diag(graph, 'manual_edges_applied') == []
    # Basic graph built without error
    assert len(graph.nodes) > 0


# ---------------------------------------------------------------------------
# Path normalization (Bug 1: backslashes, Bug 2: leading ./)
# ---------------------------------------------------------------------------

def test_backslash_source_path_resolved(tmp_path: Path) -> None:
    """Manual edge with backslash in source (e.g. data\\output.dta) matches the node."""
    project_root = tmp_path / 'proj'
    _two_script_project(project_root)

    # 'scripts\\01_build.do' should normalize to 'scripts/01_build.do'
    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts\\01_build.do',
                target='scripts/02_analysis.do',
                label='backslash-source',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    manual = _manual_edge(graph)
    assert len(manual) == 1
    edge = manual[0]
    assert edge.source == 'scripts/01_build.do'
    assert edge.target == 'scripts/02_analysis.do'
    assert edge.visible_label == 'backslash-source'


def test_backslash_target_path_resolved(tmp_path: Path) -> None:
    """Manual edge with backslash in target (e.g. data\\output.dta) matches the node."""
    project_root = tmp_path / 'proj'
    _two_script_project(project_root)

    # 'scripts\\02_analysis.do' should normalize to 'scripts/02_analysis.do'
    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='scripts\\02_analysis.do',
                label='backslash-target',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    manual = _manual_edge(graph)
    assert len(manual) == 1
    edge = manual[0]
    assert edge.source == 'scripts/01_build.do'
    assert edge.target == 'scripts/02_analysis.do'


def test_leading_dotslash_source_path_resolved(tmp_path: Path) -> None:
    """Manual edge with leading ./ in source (e.g. ./scripts/01_build.do) matches the node."""
    project_root = tmp_path / 'proj'
    _two_script_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='./scripts/01_build.do',
                target='scripts/02_analysis.do',
                label='dotslash-source',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    manual = _manual_edge(graph)
    assert len(manual) == 1
    edge = manual[0]
    assert edge.source == 'scripts/01_build.do'
    assert edge.target == 'scripts/02_analysis.do'


def test_leading_dotslash_target_path_resolved(tmp_path: Path) -> None:
    """Manual edge with leading ./ in target (e.g. ./scripts/02_analysis.do) matches the node."""
    project_root = tmp_path / 'proj'
    _two_script_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='scripts/01_build.do',
                target='./scripts/02_analysis.do',
                label='dotslash-target',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    manual = _manual_edge(graph)
    assert len(manual) == 1
    edge = manual[0]
    assert edge.source == 'scripts/01_build.do'
    assert edge.target == 'scripts/02_analysis.do'


def test_backslash_and_dotslash_combined(tmp_path: Path) -> None:
    """Manual edge with both ./ prefix and backslashes normalizes correctly."""
    project_root = tmp_path / 'proj'
    _two_script_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        manual_edges=[
            ManualEdgeConfig(
                source='.\\scripts\\01_build.do',
                target='scripts/02_analysis.do',
            )
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    manual = _manual_edge(graph)
    assert len(manual) == 1
    assert manual[0].source == 'scripts/01_build.do'
