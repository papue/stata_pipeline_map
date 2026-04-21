from pathlib import Path

from stata_pipeline_flow.config.schema import AppConfig, ManualClusterConfig, load_config
from stata_pipeline_flow.render.dot import render_dot
from stata_pipeline_flow.rules.pipeline import PipelineBuilder


def test_manual_cluster_override_reassigns_selected_nodes_and_recomputes_artifacts(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / '01_data/03_cleaned_data').mkdir(parents=True)
    (project_root / '02_analysis/02_scripts').mkdir(parents=True)
    (project_root / '02_analysis/03_outputs').mkdir(parents=True)

    (project_root / '01_data/02_scripts/01_build.do').write_text(
        'save "01_data/03_cleaned_data/panel.dta", replace\n',
        encoding='utf-8',
    )
    (project_root / '02_analysis/02_scripts/01_sample.do').write_text(
        '\n'.join(
            [
                'use "01_data/03_cleaned_data/panel.dta", clear',
                'save "02_analysis/03_outputs/sample.dta", replace',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    config = AppConfig(
        project_root=str(project_root),
        clusters=[
            ManualClusterConfig(
                cluster_id='manual_stage',
                label='Manual stage',
                members=[
                    '01_data/02_scripts/01_build.do',
                    '02_analysis/02_scripts/01_sample.do',
                ],
            )
        ],
    )

    graph = PipelineBuilder(config).build(project_root)

    assert graph.nodes['01_data/02_scripts/01_build.do'].cluster_id == 'manual_stage'
    assert graph.nodes['02_analysis/02_scripts/01_sample.do'].cluster_id == 'manual_stage'
    assert graph.nodes['01_data/03_cleaned_data/panel.dta'].cluster_id == 'manual_stage'
    assert graph.clusters['manual_stage'].label == 'Manual stage'
    assert graph.clusters['manual_stage'].metadata['kind'] == 'manual'

    dot = render_dot(graph)
    assert 'subgraph "cluster_manual_stage"' in dot
    assert 'label="Manual stage"' in dot or 'Manual stage' in dot


def test_missing_manual_cluster_member_emits_diagnostic(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / '01_data/02_scripts/01_build.do').write_text(
        'save "01_data/03_cleaned_data/panel.dta", replace\n',
        encoding='utf-8',
    )

    config = AppConfig(
        project_root=str(project_root),
        clusters=[
            ManualClusterConfig(
                cluster_id='manual_stage',
                members=['01_data/02_scripts/does_not_exist.do'],
            )
        ],
    )

    graph = PipelineBuilder(config).build(project_root)

    assert any(d.code == 'cluster_member_not_found' for d in graph.diagnostics)
    assert any(d.code == 'manual_clusters_applied' for d in graph.diagnostics)


def test_load_config_supports_root_level_clusters_section(tmp_path: Path) -> None:
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(
        '\n'.join(
            [
                'project_root: .',
                'clusters:',
                '  - id: cluster_alpha',
                '    label: Alpha',
                '    members:',
                '      - 01_data/02_scripts/01_build.do',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    config = load_config(config_path)

    assert len(config.clusters) == 1
    assert config.clusters[0].cluster_id == 'cluster_alpha'
    assert config.clusters[0].label == 'Alpha'
    assert config.clusters[0].members == ['01_data/02_scripts/01_build.do']
