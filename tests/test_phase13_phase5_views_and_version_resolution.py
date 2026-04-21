from __future__ import annotations

from pathlib import Path

from conftest import read_json, run_cli
from data_pipeline_flow.config.schema import AppConfig, DisplayConfig, ManualClusterConfig, ParserConfig, VersionFamiliesConfig
from data_pipeline_flow.render.dot import render_dot
from data_pipeline_flow.rules.pipeline import PipelineBuilder


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_version_family_prefer_highest_numeric_collapses_to_canonical_member(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    _write(
        project_root / 'main.do',
        'export delimited using "tables/results_v1.csv"\n'
        'export delimited using "tables/results_v2.csv"\n',
    )
    output_path = tmp_path / 'snapshot.json'
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(
        '\n'.join([
            'project_root: .',
            'parser:',
            '  version_families:',
            '    mode: prefer_highest_numeric',
        ]) + '\n',
        encoding='utf-8',
    )

    completed = run_cli('snapshot-json', '--project-root', str(project_root), '--config', str(config_path), '--output', str(output_path))

    assert completed.returncode == 0, completed.stderr
    payload = read_json(output_path)
    node_ids = {node['node_id'] for node in payload['nodes']}
    assert 'tables/results_v2.csv' in node_ids
    assert 'tables/results_v1.csv' not in node_ids
    codes = {diagnostic['code'] for diagnostic in payload['diagnostics']}
    assert 'version_family_resolved' in codes


def test_version_family_prefer_priority_suffix_resolves_suffix_family(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    _write(
        project_root / 'main.do',
        'export delimited using "tables/sample_draft.csv"\n'
        'export delimited using "tables/sample_final.csv"\n',
    )
    config = AppConfig(
        project_root=str(project_root),
        parser=ParserConfig(version_families=VersionFamiliesConfig(mode='prefer_priority_suffix', priority_suffixes=['final', 'draft'])),
    )

    graph = PipelineBuilder(config).build(project_root)

    assert 'tables/sample_final.csv' in graph.nodes
    assert 'tables/sample_draft.csv' not in graph.nodes
    assert any(d.code == 'version_family_resolved' for d in graph.diagnostics)


def test_scripts_only_view_bridges_hidden_artifacts_into_script_dependency(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    _write(project_root / '01_build.do', 'save "panel.dta", replace\n')
    _write(project_root / '02_analyze.do', 'use "panel.dta", clear\nexport delimited using "results.csv"\n')

    config = AppConfig(project_root=str(project_root), display=DisplayConfig(view='scripts_only'))
    graph = PipelineBuilder(config).build(project_root)
    dot = render_dot(graph, display=config.display, layout=config.layout)

    assert '"01_build.do"' in dot
    assert '"02_analyze.do"' in dot
    assert 'panel.dta' not in dot
    assert 'results.csv' not in dot
    assert '"01_build.do" -> "02_analyze.do"' in dot


def test_stage_overview_renders_cluster_summaries_and_stage_edge(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    _write(project_root / '01_data/01_build.do', 'save "01_data/panel.dta", replace\n')
    _write(project_root / '02_analysis/01_model.do', 'use "01_data/panel.dta", clear\nexport delimited using "02_analysis/results.csv"\n')

    config = AppConfig(
        project_root=str(project_root),
        display=DisplayConfig(view='stage_overview'),
        clusters=[
            ManualClusterConfig(cluster_id='data', label='Data', members=['01_data/01_build.do']),
            ManualClusterConfig(cluster_id='analysis', label='Analysis', members=['02_analysis/01_model.do']),
        ],
    )
    graph = PipelineBuilder(config).build(project_root)
    dot = render_dot(graph, display=config.display, layout=config.layout)

    assert '"cluster::data"' in dot
    assert '"cluster::analysis"' in dot
    assert 'label="Data"' in dot
    assert 'label="Analysis"' in dot
    assert '"cluster::data" -> "cluster::analysis"' in dot
    assert 'panel.dta' not in dot
