from pathlib import Path

from data_pipeline_flow.config.schema import AppConfig
from data_pipeline_flow.rules.pipeline import PipelineBuilder
from data_pipeline_flow.model.entities import Diagnostic, GraphModel
from data_pipeline_flow.validation.diagnostics import run_basic_validation


def test_pipeline_builds_real_graph() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    project_root = repo_root / 'example' / 'project'
    config = AppConfig(project_root=str(project_root))
    graph = PipelineBuilder(config).build(project_root)
    graph = run_basic_validation(graph)

    assert len(graph.nodes) > 10
    assert len(graph.edges) > 10
    assert '01_data/02_scripts/08_merge_households_transactions.do' in graph.nodes
    assert '01_data/03_cleaned_data/panel_base.dta' in graph.nodes
    assert any(edge.operation == 'merge' for edge in graph.edges)
    assert not any(d.code == 'absolute_path_usage' for d in graph.diagnostics)


def test_internal_temporary_write_is_suppressed() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    project_root = repo_root / 'example' / 'project'
    config = AppConfig(project_root=str(project_root))
    graph = PipelineBuilder(config).build(project_root)
    assert '02_analysis/03_outputs/analysis_sample.dta' in graph.nodes
    assert '01_data/03_cleaned_data/sample_working_tmp.dta' not in graph.nodes


def test_absolute_path_warnings_are_bundled_by_script() -> None:
    graph = GraphModel(project_root='.')
    graph.diagnostics = [
        Diagnostic(level='warning', code='absolute_path_usage', message='a', payload={'script': 'a.do', 'path': '/tmp/x1.dta'}),
        Diagnostic(level='warning', code='absolute_path_usage', message='b', payload={'script': 'a.do', 'path': '/tmp/x2.dta'}),
        Diagnostic(level='warning', code='absolute_path_usage', message='c', payload={'script': 'b.do', 'path': '/tmp/y1.dta'}),
    ]

    run_basic_validation(graph)

    absolute_path_diagnostics = [d for d in graph.diagnostics if d.code == 'absolute_path_usage']
    assert len(absolute_path_diagnostics) == 2

    bundled = next(d for d in absolute_path_diagnostics if d.payload.get('script') == 'a.do')
    assert bundled.payload.get('count') == '2'
    assert bundled.payload.get('unique_paths') == '2'
    assert bundled.payload.get('sample_paths') == '/tmp/x1.dta | /tmp/x2.dta'

    retained = next(d for d in absolute_path_diagnostics if d.payload.get('script') == 'b.do')
    assert retained.payload.get('path') == '/tmp/y1.dta'
