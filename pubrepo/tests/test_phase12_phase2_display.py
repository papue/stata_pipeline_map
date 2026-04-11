from __future__ import annotations

from pathlib import Path

from stata_pipeline_flow.config.schema import AppConfig
from stata_pipeline_flow.render.dot import render_dot
from stata_pipeline_flow.rules.pipeline import PipelineBuilder


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def _build_sample_graph(tmp_path: Path, **display_overrides):
    _write(tmp_path / '01_data/02_scripts/01_build.do', 'import delimited using "01_data/01_input/source.csv"\nexport delimited using "02_analysis/03_outputs/results.csv"\nsave "01_data/03_cleaned_data/panel_ready.dta"\n')
    config = AppConfig(project_root=str(tmp_path))
    for key, value in display_overrides.items():
        setattr(config.display, key, value)
    graph = PipelineBuilder(config).build(tmp_path)
    return graph, config


def test_label_path_depth_controls_folder_context(tmp_path: Path) -> None:
    graph, config = _build_sample_graph(tmp_path, label_path_depth=1)
    dot = render_dot(graph, display=config.display)
    assert 'label="03_outputs/results.csv"' in dot
    assert 'label="02_scripts/01_build.do"' in dot


def test_show_extensions_false_removes_suffixes_from_labels(tmp_path: Path) -> None:
    graph, config = _build_sample_graph(tmp_path, show_extensions=False)
    dot = render_dot(graph, display=config.display)
    assert 'label="results"' in dot
    assert 'label="01_build"' in dot
    assert 'results.csv' in dot


def test_deliverables_view_hides_intermediate_artifacts(tmp_path: Path) -> None:
    graph, config = _build_sample_graph(tmp_path, view='deliverables')
    dot = render_dot(graph, display=config.display)
    assert '02_analysis/03_outputs/results.csv' in dot
    assert '01_data/03_cleaned_data/panel_ready.dta' not in dot
    assert '01_data/02_scripts/01_build.do' in dot


def test_theme_preset_is_stable_in_rendered_dot(tmp_path: Path) -> None:
    graph, config = _build_sample_graph(tmp_path, theme='modern-dark')
    dot = render_dot(graph, display=config.display)
    assert 'bgcolor="#1E1F24"' in dot
    assert 'fillcolor="#2F3B52"' in dot


def test_placeholder_style_can_be_filled_dashed(tmp_path: Path) -> None:
    _write(tmp_path / 'main.do', 'save "results_`unknown\'.csv"\n')
    config = AppConfig(project_root=str(tmp_path))
    config.display.placeholder_style = 'filled_dashed'
    graph = PipelineBuilder(config).build(tmp_path)
    dot = render_dot(graph, display=config.display)
    assert 'style="dashed,filled"' in dot
