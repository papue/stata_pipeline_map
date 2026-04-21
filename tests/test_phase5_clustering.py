from pathlib import Path

from stata_pipeline_flow.config.schema import AppConfig
from stata_pipeline_flow.render.dot import render_dot
from stata_pipeline_flow.rules.pipeline import PipelineBuilder


def test_linear_chain_in_same_folder_forms_single_cluster_and_renders_subgraph(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / '01_data/01_input').mkdir(parents=True)
    (project_root / '01_data/03_cleaned_data').mkdir(parents=True)
    (project_root / '01_data/01_input/source.csv').write_text('x\n1\n', encoding='utf-8')

    (project_root / '01_data/02_scripts/01_build.do').write_text(
        '\n'.join(
            [
                'import delimited "01_data/01_input/source.csv", clear',
                'save "01_data/03_cleaned_data/a.dta", replace',
            ]
        )
        + '\n',
        encoding='utf-8',
    )
    (project_root / '01_data/02_scripts/02_transform.do').write_text(
        '\n'.join(
            [
                'use "01_data/03_cleaned_data/a.dta", clear',
                'save "01_data/03_cleaned_data/b.dta", replace',
            ]
        )
        + '\n',
        encoding='utf-8',
    )
    (project_root / '01_data/02_scripts/03_export.do').write_text(
        '\n'.join(
            [
                'use "01_data/03_cleaned_data/b.dta", clear',
                'export delimited using "01_data/03_cleaned_data/final.csv", replace',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    graph = PipelineBuilder(AppConfig(project_root=str(project_root))).build(project_root)
    script_clusters = {
        graph.nodes['01_data/02_scripts/01_build.do'].cluster_id,
        graph.nodes['01_data/02_scripts/02_transform.do'].cluster_id,
        graph.nodes['01_data/02_scripts/03_export.do'].cluster_id,
    }

    assert len(script_clusters) == 1
    cluster_id = next(iter(script_clusters))
    assert cluster_id is not None
    assert graph.nodes['01_data/03_cleaned_data/b.dta'].cluster_id == cluster_id
    assert len(graph.clusters) == 1

    dot = render_dot(graph)
    assert f'subgraph "cluster_{cluster_id}"' in dot
    assert '01_data/02_scripts' in dot


def test_different_script_folders_stay_in_separate_clusters(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / '01_data/03_cleaned_data').mkdir(parents=True)
    (project_root / '02_analysis/02_scripts').mkdir(parents=True)
    (project_root / '02_analysis/03_outputs').mkdir(parents=True)

    (project_root / '01_data/02_scripts/01_build.do').write_text(
        'save "01_data/03_cleaned_data/panel.dta", replace\n',
        encoding='utf-8',
    )
    (project_root / '01_data/02_scripts/02_prepare.do').write_text(
        'save "01_data/03_cleaned_data/aux.dta", replace\n',
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
    (project_root / '02_analysis/02_scripts/02_tables.do').write_text(
        '\n'.join(
            [
                'use "02_analysis/03_outputs/sample.dta", clear',
                'export delimited using "02_analysis/03_outputs/table.csv", replace',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    graph = PipelineBuilder(AppConfig(project_root=str(project_root))).build(project_root)

    data_cluster = graph.nodes['01_data/02_scripts/01_build.do'].cluster_id
    analysis_cluster = graph.nodes['02_analysis/02_scripts/01_sample.do'].cluster_id

    assert data_cluster is not None
    assert analysis_cluster is not None
    assert data_cluster != analysis_cluster
    assert graph.nodes['01_data/02_scripts/02_prepare.do'].cluster_id == data_cluster
    assert graph.nodes['02_analysis/02_scripts/02_tables.do'].cluster_id == analysis_cluster
    assert graph.nodes['01_data/03_cleaned_data/panel.dta'].cluster_id is None
    assert graph.nodes['02_analysis/03_outputs/sample.dta'].cluster_id == analysis_cluster
    assert len(graph.clusters) == 2
