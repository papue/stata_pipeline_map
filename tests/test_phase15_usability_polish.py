from __future__ import annotations

from pathlib import Path

from conftest import run_cli
from data_pipeline_flow.config.schema import AppConfig, DisplayConfig
from data_pipeline_flow.render.dot import render_dot
from data_pipeline_flow.rules.pipeline import PipelineBuilder


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_show_temporary_outputs_renders_erased_temporary_artifact(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    _write(
        project_root / 'main.do',
        'save "work/sample_tmp.dta", replace\n'
        'erase "work/sample_tmp.dta"\n',
    )

    config = AppConfig(project_root=str(project_root), display=DisplayConfig(show_temporary_outputs=True))
    graph = PipelineBuilder(config).build(project_root)
    dot = render_dot(graph, display=config.display, layout=config.layout)

    assert 'work/sample_tmp.dta' in graph.nodes
    assert graph.nodes['work/sample_tmp.dta'].metadata.get('erased') == 'true'
    assert '"main.do" -> "work/sample_tmp.dta"' in dot
    assert 'style="dashed"' in dot
    assert any(d.code == 'temporary_outputs_rendered' for d in graph.diagnostics)


def test_scripts_only_view_emits_irrelevant_setting_diagnostic(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    _write(project_root / '01_build.do', 'save "panel_tmp.dta", replace\n')

    config = AppConfig(
        project_root=str(project_root),
        display=DisplayConfig(view='scripts_only', show_temporary_outputs=True),
    )
    graph = PipelineBuilder(config).build(project_root)

    messages = [d.message for d in graph.diagnostics if d.code == 'display_option_irrelevant']
    assert any('show_temporary_outputs' in message for message in messages)


def test_render_dot_cli_prints_config_effects_summary(tmp_path: Path) -> None:
    project_root = tmp_path / 'project'
    _write(
        project_root / 'main.do',
        'export delimited using "tables/results_v1.csv"\n'
        'export delimited using "tables/results_v2.csv"\n',
    )
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
    output_path = tmp_path / 'graph.dot'

    completed = run_cli('render-dot', '--project-root', str(project_root), '--config', str(config_path), '--output', str(output_path))

    assert completed.returncode == 0, completed.stderr
    assert 'Config effects:' in completed.stdout
    assert 'Version families collapsed: 1' in completed.stdout
