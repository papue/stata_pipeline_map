from __future__ import annotations

from pathlib import Path

from conftest import read_json, run_cli
from data_pipeline_flow.config.schema import load_config
from data_pipeline_flow.render.dot import render_dot
from data_pipeline_flow.rules.pipeline import PipelineBuilder


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_snapshot_json_command_writes_graph_snapshot(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    _write(project_root / 'main.do', 'export delimited using "tables/results.csv"\n')
    output_path = tmp_path / 'snapshot.json'

    completed = run_cli('snapshot-json', '--project-root', str(project_root), '--output', str(output_path))

    assert completed.returncode == 0, completed.stderr
    payload = read_json(output_path)
    node_ids = {node['node_id'] for node in payload['nodes']}
    assert 'main.do' in node_ids
    assert 'tables/results.csv' in node_ids
    assert payload['config']['display']['theme'] == 'modern-light'


def test_end_to_end_snapshot_captures_version_family_and_loop_outputs(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    _write(
        project_root / 'main.do',
        'foreach year in 2022 2023 {\n'
        '    export delimited using "tables/output_`year\'.csv"\n'
        '}\n'
        'export delimited using "tables/sample_v1.csv"\n'
        'export delimited using "tables/sample_v2.csv"\n',
    )
    output_path = tmp_path / 'snapshot.json'

    completed = run_cli('snapshot-json', '--project-root', str(project_root), '--output', str(output_path))

    assert completed.returncode == 0, completed.stderr
    payload = read_json(output_path)
    node_ids = {node['node_id'] for node in payload['nodes']}
    assert 'tables/output_2022.csv' in node_ids
    assert 'tables/output_2023.csv' in node_ids
    codes = {diagnostic['code'] for diagnostic in payload['diagnostics']}
    assert 'version_family_detected' in codes


def test_invalid_display_values_fall_back_safely(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    _write(project_root / 'main.do', 'save "results_`unknown\'.csv"\n')
    config_path = tmp_path / 'config.yaml'
    config_path.write_text(
        '\n'.join(
            [
                'project_root: .',
                'display:',
                '  theme: neon-future',
                '  view: sideways',
                '  node_label_style: alias_then_path_depth',
                '  placeholder_style: hidden',
                '  edge_label_mode: essential',
                '  label_path_depth: -4',
                '  show_extensions: maybe',
            ]
        )
        + '\n',
        encoding='utf-8',
    )

    config = load_config(config_path)
    config.project_root = str(project_root)
    graph = PipelineBuilder(config).build(project_root)
    dot = render_dot(graph, display=config.display, layout=config.layout)

    assert config.display.theme == 'modern-light'
    assert config.display.view == 'overview'
    assert config.display.node_label_style == 'basename'
    assert config.display.placeholder_style == 'dashed'
    assert config.display.edge_label_mode == 'auto'
    assert config.display.label_path_depth == 0
    assert config.display.show_extensions is True
    assert 'fillcolor="#EEF3FF"' in dot
    assert 'style="dashed"' in dot


def test_docs_and_examples_exist_for_phase4() -> None:
    assert Path('docs/migration.md').exists()
    assert Path('docs/examples/minimal_config.yaml').exists()
    assert Path('docs/examples/advanced_config.yaml').exists()


def test_extract_edges_output_resolves_relative_to_cwd_not_project_root(tmp_path: Path) -> None:
    project_root = tmp_path / 'myproject'
    _write(project_root / 'main.do', 'save "results.dta", replace\n')
    output_path = tmp_path / 'edges.csv'

    # Pass --output as an absolute path to ensure it lands where specified, not under project_root
    completed = run_cli(
        'extract-edges',
        '--project-root', str(project_root),
        '--output', str(output_path),
    )

    assert completed.returncode == 0, completed.stderr
    assert output_path.exists(), (
        f'edges.csv was not written to {output_path}. '
        f'stdout: {completed.stdout!r}'
    )
    # Must NOT have written inside the project root
    wrong_path = project_root / 'edges.csv'
    assert not wrong_path.exists(), 'edges.csv was incorrectly written inside project_root'
