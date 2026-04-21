from __future__ import annotations

from pathlib import Path

from data_pipeline_flow.config.schema import AppConfig
from data_pipeline_flow.model.normalize import to_project_relative
from data_pipeline_flow.rules.pipeline import PipelineBuilder


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_relative_path_stays_project_relative(tmp_path: Path) -> None:
    target = tmp_path / '01_data' / '03_cleaned_data' / 'panel_base.dta'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('', encoding='utf-8')

    normalized, was_absolute = to_project_relative(
        tmp_path,
        '01_data/03_cleaned_data/panel_base.dta',
    )

    assert was_absolute is False
    assert normalized == '01_data/03_cleaned_data/panel_base.dta'


def test_foreach_of_local_outputs_are_concretely_resolved(tmp_path: Path) -> None:
    _write(
        tmp_path / 'main.do',
        'local years 2022 2023\n'
        'foreach year of local years {\n'
        '    export delimited using "out_`year\'.csv"\n'
        '}\n',
    )
    config = AppConfig(project_root=str(tmp_path))
    graph = PipelineBuilder(config).build(tmp_path)

    assert 'out_2022.csv' in graph.nodes
    assert 'out_2023.csv' in graph.nodes
    assert 'out_{year}.csv' not in graph.nodes
