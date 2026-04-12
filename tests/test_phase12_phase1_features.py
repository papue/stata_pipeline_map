from __future__ import annotations

from pathlib import Path

from stata_pipeline_flow.config.schema import AppConfig
from stata_pipeline_flow.render.dot import render_dot
from stata_pipeline_flow.rules.pipeline import PipelineBuilder


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_loop_generated_outputs_are_concretely_resolved(tmp_path: Path) -> None:
    _write(
        tmp_path / 'main.do',
        'foreach year in 2022 2023 {\n'
        '    export delimited using "out_`year\'.csv"\n'
        '}\n',
    )
    config = AppConfig(project_root=str(tmp_path))
    graph = PipelineBuilder(config).build(tmp_path)

    assert 'out_2022.csv' in graph.nodes
    assert 'out_2023.csv' in graph.nodes
    assert all(node.role == 'deliverable' for key, node in graph.nodes.items() if key.startswith('out_'))


def test_unresolved_dynamic_output_becomes_placeholder_node(tmp_path: Path) -> None:
    _write(tmp_path / 'main.do', 'save "results_`unknown\'.csv"\n')
    config = AppConfig(project_root=str(tmp_path))
    graph = PipelineBuilder(config).build(tmp_path)

    placeholder_id = 'results_{unknown}.csv'
    assert placeholder_id in graph.nodes
    node = graph.nodes[placeholder_id]
    assert node.node_type == 'artifact_placeholder'
    assert node.role == 'placeholder_artifact'
    assert any(d.code == 'dynamic_path_partial_resolution' for d in graph.diagnostics)

    dot = render_dot(graph)
    assert placeholder_id in dot
    assert 'style="dashed"' in dot


def test_temporary_outputs_stay_hidden_by_default(tmp_path: Path) -> None:
    _write(tmp_path / 'main.do', 'save "scratch_tmp.dta"\n')
    config = AppConfig(project_root=str(tmp_path))
    graph = PipelineBuilder(config).build(tmp_path)

    assert 'scratch_tmp.dta' not in graph.nodes


def test_terminal_deliverable_outputs_show_by_default(tmp_path: Path) -> None:
    _write(tmp_path / 'main.do', 'export delimited using "tables/results.csv"\n')
    config = AppConfig(project_root=str(tmp_path))
    graph = PipelineBuilder(config).build(tmp_path)

    assert 'tables/results.csv' in graph.nodes
    assert graph.nodes['tables/results.csv'].role == 'deliverable'


def test_version_family_detection_emits_diagnostic(tmp_path: Path) -> None:
    _write(tmp_path / 'main.do', 'export delimited using "data/sample_v1.csv"\nexport delimited using "data/sample_v2.csv"\n')
    config = AppConfig(project_root=str(tmp_path))
    graph = PipelineBuilder(config).build(tmp_path)

    codes = [diagnostic.code for diagnostic in graph.diagnostics]
    assert 'version_family_detected' in codes
