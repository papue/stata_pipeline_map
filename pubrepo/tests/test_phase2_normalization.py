from pathlib import Path

from stata_pipeline_flow.config.schema import AppConfig, ExclusionConfig
from stata_pipeline_flow.model.normalize import to_project_relative
from stata_pipeline_flow.parser.discovery import discover_project_files
from stata_pipeline_flow.rules.exclusions import resolve_exclusion_config
from stata_pipeline_flow.rules.pipeline import PipelineBuilder


def test_to_project_relative_strips_foreign_absolute_root_by_project_name(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    project_root.mkdir()
    normalized, was_absolute = to_project_relative(
        project_root,
        '/foreign/machine/stata_realistic_project/01_data/03_cleaned_data/panel_base.dta',
    )
    assert was_absolute is True
    assert normalized == '01_data/03_cleaned_data/panel_base.dta'



def test_relative_project_root_uses_resolved_project_name(monkeypatch, tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    project_root.mkdir()
    monkeypatch.chdir(project_root)

    normalized, was_absolute = to_project_relative(
        Path('.'),
        '/foreign/machine/stata_realistic_project/02_analysis/03_outputs/table.csv',
    )
    assert was_absolute is True
    assert normalized == '02_analysis/03_outputs/table.csv'


def test_discovery_prunes_excluded_directories_and_exact_files(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / 'archive/02_scripts').mkdir(parents=True)
    (project_root / 'viewer_output').mkdir(parents=True)

    (project_root / '01_data/02_scripts/keep.do').write_text('display "ok"\n', encoding='utf-8')
    (project_root / '01_data/02_scripts/skip_me.do').write_text('display "skip"\n', encoding='utf-8')
    (project_root / 'archive/02_scripts/old.do').write_text('display "old"\n', encoding='utf-8')
    (project_root / 'viewer_output/rendered.dot').write_text('digraph {}\n', encoding='utf-8')

    config = AppConfig(project_root=str(project_root))
    config.exclusions = ExclusionConfig(
        prefixes=['viewer_output/'],
        globs=['*.tmp'],
        exact_names=['skip_me.do'],
        folder_names=['archive'],
    )

    scan = discover_project_files(project_root, resolve_exclusion_config(config.exclusions), config.normalization)
    assert '01_data/02_scripts/keep.do' in scan.do_files
    assert '01_data/02_scripts/skip_me.do' not in scan.do_files
    assert 'archive/02_scripts/old.do' not in scan.do_files
    assert 'archive/' in scan.excluded_files
    assert 'viewer_output/' in scan.excluded_files


def test_mixed_path_spellings_collapse_to_single_relative_node(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/01_input').mkdir(parents=True)
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / '01_data/03_cleaned_data').mkdir(parents=True)
    (project_root / '01_data/01_input/source.csv').write_text('x\n1\n', encoding='utf-8')

    (project_root / '01_data/02_scripts/01_build.do').write_text(
        '\n'.join(
            [
                'global root "C:/temp/stata_realistic_project"',
                'import delimited "$root\\01_data\\01_input\\source.csv", clear',
                'save "$root/01_data/03_cleaned_data/output.dta", replace',
            ]
        )
        + '\n',
        encoding='utf-8',
    )
    (project_root / '01_data/02_scripts/02_use.do').write_text(
        '\n'.join(
            [
                'use "./01_data/03_cleaned_data/output.dta", clear',
                'save "01_data/03_cleaned_data/final.dta", replace',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    graph = PipelineBuilder(AppConfig(project_root=str(project_root))).build(project_root)
    output_nodes = [node_id for node_id in graph.nodes if node_id == '01_data/03_cleaned_data/output.dta']
    assert output_nodes == ['01_data/03_cleaned_data/output.dta']
    assert all(not node_id.startswith(str(project_root)) for node_id in graph.nodes)


def test_exclusion_presets_expand_human_friendly_config(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / 'old/02_scripts').mkdir(parents=True)
    (project_root / 'viewer_output').mkdir(parents=True)

    (project_root / '01_data/02_scripts/keep.do').write_text('display "ok"\n', encoding='utf-8')
    (project_root / 'old/02_scripts/old_job.do').write_text('display "legacy"\n', encoding='utf-8')
    (project_root / 'viewer_output/flow.dot').write_text('digraph {}\n', encoding='utf-8')

    exclusions = resolve_exclusion_config(
        ExclusionConfig(
            prefixes=[],
            globs=[],
            folder_names=[],
            presets=['generated_outputs', 'archival_folders'],
        )
    )
    scan = discover_project_files(project_root, exclusions, AppConfig().normalization)

    assert '01_data/02_scripts/keep.do' in scan.do_files
    assert 'old/02_scripts/old_job.do' not in scan.do_files
    assert 'viewer_output/' in scan.excluded_files
    assert 'old/' in scan.excluded_files


def test_excluded_references_are_omitted_but_reported(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/01_input').mkdir(parents=True)
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / 'archive/01_input').mkdir(parents=True)
    (project_root / '01_data/01_input/live.csv').write_text('x\n1\n', encoding='utf-8')
    (project_root / 'archive/01_input/old.csv').write_text('x\n0\n', encoding='utf-8')

    (project_root / '01_data/02_scripts/01_use.do').write_text(
        '\n'.join(
            [
                'import delimited "01_data/01_input/live.csv", clear',
                'append using "archive/01_input/old.csv"',
                'save "01_data/01_input/combined.dta", replace',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    config = AppConfig(project_root=str(project_root))
    config.exclusions = ExclusionConfig(
        prefixes=[],
        globs=[],
        folder_names=['archive'],
    )
    graph = PipelineBuilder(config).build(project_root)

    assert 'archive/01_input/old.csv' not in graph.nodes
    assert not any(edge.source == 'archive/01_input/old.csv' for edge in graph.edges)
    excluded_refs = [d for d in graph.diagnostics if d.code == 'excluded_reference']
    assert len(excluded_refs) == 1
    assert excluded_refs[0].payload['path'] == 'archive/01_input/old.csv'
    assert excluded_refs[0].payload['command'] == 'append'


def test_default_exclusions_are_expressed_through_presets(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / 'viewer_output').mkdir(parents=True)
    (project_root / 'archive/02_scripts').mkdir(parents=True)
    (project_root / '.git').mkdir(parents=True)

    (project_root / '01_data/02_scripts/keep.do').write_text('display "ok"\n', encoding='utf-8')
    (project_root / 'archive/02_scripts/old_job.do').write_text('display "legacy"\n', encoding='utf-8')
    (project_root / 'viewer_output/flow.dot').write_text('digraph {}\n', encoding='utf-8')
    (project_root / '.git/config').write_text('[core]\n', encoding='utf-8')

    config = AppConfig(project_root=str(project_root))
    resolved = resolve_exclusion_config(config.exclusions)
    scan = discover_project_files(project_root, resolved, config.normalization)

    assert config.exclusions.presets == ['generated_outputs', 'archival_folders', 'python_runtime']
    assert '01_data/02_scripts/keep.do' in scan.do_files
    assert 'archive/' in scan.excluded_files
    assert 'viewer_output/' in scan.excluded_files
    assert '.git/' in scan.excluded_files


def test_cli_warns_when_custom_exclusions_do_not_inherit_default_presets(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / '01_data/02_scripts').mkdir(parents=True)
    (project_root / 'archive/02_scripts').mkdir(parents=True)
    (project_root / '01_data/02_scripts/keep.do').write_text('display "ok"\n', encoding='utf-8')
    (project_root / 'archive/02_scripts/old_job.do').write_text('display "legacy"\n', encoding='utf-8')

    config = AppConfig(project_root=str(project_root))
    config.exclusions = ExclusionConfig(presets=[], folder_names=['scratch'])
    graph = PipelineBuilder(config).build(project_root)

    warning = next((d for d in graph.diagnostics if d.code == 'exclusion_defaults_not_inherited'), None)
    assert warning is not None
    assert 'viewer_output' in warning.message
    assert 'archive' in warning.message
