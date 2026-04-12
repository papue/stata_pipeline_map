from pathlib import Path

from stata_pipeline_flow.config.schema import AppConfig, ManualClusterConfig
from stata_pipeline_flow.rules.pipeline import PipelineBuilder
from stata_pipeline_flow.validation.diagnostics import build_validation_report, run_basic_validation


def _build_two_stage_project(project_root: Path) -> None:
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



def test_duplicate_manual_cluster_ids_emit_diagnostic_without_changing_override_order(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    _build_two_stage_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        clusters=[
            ManualClusterConfig(
                cluster_id='manual_stage',
                label='First label',
                members=['01_data/02_scripts/01_build.do'],
            ),
            ManualClusterConfig(
                cluster_id='manual_stage',
                label='Second label',
                members=['02_analysis/02_scripts/01_sample.do'],
            ),
        ],
    )

    graph = PipelineBuilder(config).build(project_root)

    duplicate_id = [d for d in graph.diagnostics if d.code == 'duplicate_manual_cluster_id']
    assert len(duplicate_id) == 1
    assert duplicate_id[0].payload['cluster_id'] == 'manual_stage'
    assert duplicate_id[0].payload['entries'] == '1,2'

    assert graph.nodes['01_data/02_scripts/01_build.do'].cluster_id == 'manual_stage'
    assert graph.nodes['02_analysis/02_scripts/01_sample.do'].cluster_id == 'manual_stage'
    assert graph.clusters['manual_stage'].label == 'Second label'



def test_duplicate_manual_cluster_member_emits_diagnostic_and_later_cluster_still_wins(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    _build_two_stage_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        clusters=[
            ManualClusterConfig(
                cluster_id='cluster_alpha',
                members=['01_data/02_scripts/01_build.do'],
            ),
            ManualClusterConfig(
                cluster_id='cluster_beta',
                members=['01_data/02_scripts/01_build.do'],
            ),
        ],
    )

    graph = PipelineBuilder(config).build(project_root)

    duplicate_member = [d for d in graph.diagnostics if d.code == 'duplicate_manual_cluster_member']
    assert len(duplicate_member) == 1
    assert duplicate_member[0].payload['member'] == '01_data/02_scripts/01_build.do'
    assert duplicate_member[0].payload['cluster_ids'] == 'cluster_alpha|cluster_beta'

    assert graph.nodes['01_data/02_scripts/01_build.do'].cluster_id == 'cluster_beta'



def test_empty_manual_cluster_emits_diagnostic_and_is_visible_in_validation_report(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    _build_two_stage_project(project_root)

    config = AppConfig(
        project_root=str(project_root),
        clusters=[ManualClusterConfig(cluster_id='empty_cluster', label='Empty cluster', members=[])],
    )

    graph = PipelineBuilder(config).build(project_root)
    graph = run_basic_validation(graph)
    report = build_validation_report(graph)

    empty_cluster = [d for d in graph.diagnostics if d.code == 'empty_manual_cluster']
    assert len(empty_cluster) == 1
    assert empty_cluster[0].payload['cluster_id'] == 'empty_cluster'
    assert 'empty_cluster' in empty_cluster[0].message
    assert 'empty_manual_cluster' in report['summary']['by_code']
    assert report['summary']['by_code']['empty_manual_cluster'] == 1
    assert 'empty_cluster' not in graph.clusters
