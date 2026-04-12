from __future__ import annotations

from pathlib import Path

from stata_pipeline_flow.config.schema import AppConfig, ManualClusterConfig, load_config
from stata_pipeline_flow.render.dot import render_dot
from stata_pipeline_flow.rules.pipeline import PipelineBuilder


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _build_two_stage_project(project_root: Path) -> None:
    _write(project_root / '01_data/02_scripts/01_build.do', 'save "01_data/03_cleaned_data/panel.dta", replace\n')
    _write(project_root / '02_analysis/02_scripts/01_sample.do', 'use "01_data/03_cleaned_data/panel.dta", clear\nsave "02_analysis/03_outputs/sample.dta", replace\n')


def test_manual_cluster_lane_and_order_control_sorted_clusters(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    _build_two_stage_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        clusters=[
            ManualClusterConfig(cluster_id='robustness', members=['02_analysis/02_scripts/01_sample.do'], lane='parallel', order=2),
            ManualClusterConfig(cluster_id='data_prep', members=['01_data/02_scripts/01_build.do'], lane='main', order=1),
        ],
    )
    graph = PipelineBuilder(config).build(project_root)

    sorted_ids = [cluster.cluster_id for cluster in graph.sorted_clusters()]
    assert sorted_ids[:2] == ['data_prep', 'robustness']


def test_same_lane_rendering_emits_rank_same_group(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    _build_two_stage_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        clusters=[
            ManualClusterConfig(cluster_id='cluster_a', members=['01_data/02_scripts/01_build.do'], lane='main', order=1),
            ManualClusterConfig(cluster_id='cluster_b', members=['02_analysis/02_scripts/01_sample.do'], lane='main', order=2),
        ],
    )
    graph = PipelineBuilder(config).build(project_root)
    dot = render_dot(graph, display=config.display, layout=config.layout)

    assert 'subgraph "lane::main" {' in dot
    assert 'rank="same";' in dot


def test_layout_cluster_lanes_missing_cluster_emits_warning(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    _build_two_stage_project(project_root)

    config_path = tmp_path / 'config.yaml'
    config_path.write_text(
        '\n'.join(
            [
                'project_root: .',
                'layout:',
                '  cluster_lanes:',
                '    - lane: main',
                '      cluster_ids:',
                '        - missing_cluster',
            ]
        ) + '\n',
        encoding='utf-8',
    )
    config = load_config(config_path)
    config.project_root = str(project_root)
    graph = PipelineBuilder(config).build(project_root)

    diagnostics = [d for d in graph.diagnostics if d.code == 'layout_lane_missing_cluster']
    assert len(diagnostics) == 1
    assert diagnostics[0].payload['cluster_id'] == 'missing_cluster'


def test_collapsed_cluster_renders_summary_node_and_aggregated_edges(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    _write(project_root / '01_data/02_scripts/01_build.do', 'save "01_data/03_cleaned_data/panel.dta", replace\n')
    _write(project_root / '02_analysis/02_scripts/01_sample.do', 'use "01_data/03_cleaned_data/panel.dta", clear\nsave "02_analysis/03_outputs/sample.dta", replace\n')
    _write(project_root / '03_tables/02_scripts/01_export.do', 'use "02_analysis/03_outputs/sample.dta", clear\nexport delimited using "03_tables/03_outputs/final.csv"\n')

    config = AppConfig(
        project_root=str(project_root),
        clusters=[
            ManualClusterConfig(cluster_id='analysis', label='Analysis', members=['02_analysis/02_scripts/01_sample.do'], collapse=True),
            ManualClusterConfig(cluster_id='prep', members=['01_data/02_scripts/01_build.do']),
            ManualClusterConfig(cluster_id='tables', members=['03_tables/02_scripts/01_export.do']),
        ],
    )
    graph = PipelineBuilder(config).build(project_root)
    dot = render_dot(graph, display=config.display, layout=config.layout)

    assert '"cluster::analysis"' in dot
    assert 'label="Analysis"' in dot
    assert '"02_analysis/02_scripts/01_sample.do" [' not in dot
    assert '"cluster::analysis" -> "03_tables/02_scripts/01_export.do"' in dot
    assert '"01_data/02_scripts/01_build.do" -> "cluster::analysis"' in dot


def test_invalid_layout_rankdir_falls_back_to_lr(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    _build_two_stage_project(project_root)

    config = AppConfig(project_root=str(project_root))
    config.layout.rankdir = 'DIAGONAL'
    graph = PipelineBuilder(config).build(project_root)
    dot = render_dot(graph, display=config.display, layout=config.layout)

    assert 'rankdir=LR;' in dot
    assert any(d.code == 'invalid_layout_rankdir' for d in graph.diagnostics)
