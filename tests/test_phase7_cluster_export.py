from argparse import Namespace
from pathlib import Path

from stata_pipeline_flow.cli.main import command_export_clusters
from stata_pipeline_flow.config.export import build_cluster_export_document
from stata_pipeline_flow.config.schema import AppConfig, ManualClusterConfig
from stata_pipeline_flow.rules.pipeline import PipelineBuilder



def test_cluster_export_document_contains_script_members_only(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / '01_data/03_cleaned_data').mkdir(parents=True)
    (project_root / '01_data/02_scripts/01_build.do').write_text(
        '\n'.join(
            [
                'save "01_data/03_cleaned_data/panel.dta", replace',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    graph = PipelineBuilder(AppConfig(project_root=str(project_root))).build(project_root)
    document = build_cluster_export_document(graph)

    assert 'clusters:' in document
    assert '  - id: "cluster_001"' in document
    assert '      - "01_data/02_scripts/01_build.do"' in document
    assert '01_data/03_cleaned_data/panel.dta' not in document



def test_export_clusters_auto_mode_ignores_manual_override_config(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / '02_analysis/02_scripts').mkdir(parents=True)
    (project_root / '01_data/03_cleaned_data').mkdir(parents=True)
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

    output_path = tmp_path / 'clusters_auto.yaml'
    args = Namespace(
        project_root=str(project_root),
        config=None,
        edge_csv='viewer_output/parser_edges.csv',
        output=str(output_path),
        mode='auto',
    )
    command_export_clusters(args)
    text = output_path.read_text(encoding='utf-8')

    assert 'id: "cluster_001"' in text
    assert 'id: "cluster_002"' in text

    config_path = tmp_path / 'manual.yaml'
    config_path.write_text(
        '\n'.join(
            [
                'project_root: .',
                'clusters:',
                '  - id: custom_manual',
                '    label: Custom manual',
                '    members:',
                '      - 01_data/02_scripts/01_build.do',
                '      - 02_analysis/02_scripts/01_sample.do',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    output_path_with_config = tmp_path / 'clusters_auto_from_config.yaml'
    args_with_config = Namespace(
        project_root=str(project_root),
        config=str(config_path),
        edge_csv='viewer_output/parser_edges.csv',
        output=str(output_path_with_config),
        mode='auto',
    )
    command_export_clusters(args_with_config)
    text_with_config = output_path_with_config.read_text(encoding='utf-8')

    assert 'id: "cluster_001"' in text_with_config
    assert 'id: "cluster_002"' in text_with_config
    assert 'custom_manual' not in text_with_config



def test_export_clusters_resolved_mode_can_emit_manual_cluster_ids(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / '02_analysis/02_scripts').mkdir(parents=True)
    (project_root / '01_data/03_cleaned_data').mkdir(parents=True)
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
    config_path = tmp_path / 'resolved.yaml'
    config_path.write_text(
        '\n'.join(
            [
                'project_root: .',
                'clusters:',
                '  - id: manual_stage',
                '    label: Manual stage',
                '    members:',
                '      - 01_data/02_scripts/01_build.do',
                '      - 02_analysis/02_scripts/01_sample.do',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    output_path = tmp_path / 'clusters_resolved.yaml'
    args = Namespace(
        project_root=str(project_root),
        config=str(config_path),
        edge_csv='viewer_output/parser_edges.csv',
        output=str(output_path),
        mode='resolved',
    )
    command_export_clusters(args)
    text = output_path.read_text(encoding='utf-8')

    assert 'id: "manual_stage"' in text
    assert 'label: "Manual stage"' in text
    assert '01_data/03_cleaned_data/panel.dta' not in text
