from pathlib import Path
import json

from stata_pipeline_flow.config.schema import AppConfig
from stata_pipeline_flow.model.entities import Edge, GraphModel, Node
from stata_pipeline_flow.validation.diagnostics import build_validation_report, run_basic_validation, write_validation_report


def test_validation_flags_missing_inputs_and_multiple_writers(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / 'scripts').mkdir(parents=True)
    (project_root / 'scripts/step_a.do').write_text('display "a"\n', encoding='utf-8')
    (project_root / 'scripts/step_b.do').write_text('display "b"\n', encoding='utf-8')

    graph = GraphModel(project_root=str(project_root))
    graph.add_node(Node(node_id='scripts/step_a.do', label='step_a.do', node_type='script', path='scripts/step_a.do', role='script'))
    graph.add_node(Node(node_id='scripts/step_b.do', label='step_b.do', node_type='script', path='scripts/step_b.do', role='script'))
    graph.add_node(Node(node_id='data/missing_input.csv', label='missing_input.csv', node_type='artifact', path='data/missing_input.csv', role='original_input'))
    graph.add_node(Node(node_id='data/shared_output.dta', label='shared_output.dta', node_type='artifact', path='data/shared_output.dta', role='generated_dta'))

    graph.add_edge(Edge(source='data/missing_input.csv', target='scripts/step_a.do', operation='import', kind='original_input', visible_label='import'))
    graph.add_edge(Edge(source='scripts/step_a.do', target='data/shared_output.dta', operation='save', kind='generated_dta', visible_label='save'))
    graph.add_edge(Edge(source='scripts/step_b.do', target='data/shared_output.dta', operation='save', kind='generated_dta', visible_label='save'))

    graph = run_basic_validation(graph)
    codes = [d.code for d in graph.diagnostics]
    assert 'missing_referenced_file' in codes
    assert 'multiple_writers' in codes
    assert 'unconsumed_output' in codes


def test_validation_detects_cycle_and_ambiguous_names(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    (project_root / 'stage_a').mkdir(parents=True)
    (project_root / 'stage_b').mkdir(parents=True)
    (project_root / 'stage_a/run.do').write_text('display "a"\n', encoding='utf-8')
    (project_root / 'stage_b/run.do').write_text('display "b"\n', encoding='utf-8')

    graph = GraphModel(project_root=str(project_root))
    graph.add_node(Node(node_id='stage_a/run.do', label='run.do', node_type='script', path='stage_a/run.do', role='script'))
    graph.add_node(Node(node_id='stage_b/run.do', label='run.do', node_type='script', path='stage_b/run.do', role='script'))
    graph.add_edge(Edge(source='stage_a/run.do', target='stage_b/run.do', operation='do', kind='script_call'))
    graph.add_edge(Edge(source='stage_b/run.do', target='stage_a/run.do', operation='do', kind='script_call'))

    graph = run_basic_validation(graph)
    codes = [d.code for d in graph.diagnostics]
    assert 'cycle_detected' in codes
    assert 'ambiguous_name' in codes


def test_validation_report_writes_json_summary(tmp_path: Path) -> None:
    project_root = tmp_path / 'stata_realistic_project'
    project_root.mkdir()
    graph = GraphModel(project_root=str(project_root))
    graph.add_node(Node(node_id='lonely.do', label='lonely.do', node_type='script', path='lonely.do', role='script'))
    graph = run_basic_validation(graph)

    output_path = tmp_path / 'validation_report.json'
    write_validation_report(graph, output_path)

    payload = json.loads(output_path.read_text(encoding='utf-8'))
    assert payload['summary']['nodes'] == 1
    assert payload['summary']['diagnostics'] >= 1
    assert any(item['code'] == 'orphan_node' for item in payload['diagnostics'])


def test_real_project_validation_report_contains_exclusion_inventory() -> None:
    project_root = Path(__file__).resolve().parents[1]
    config = AppConfig(project_root=str(project_root))
    from stata_pipeline_flow.rules.pipeline import PipelineBuilder

    graph = PipelineBuilder(config).build(project_root)
    graph = run_basic_validation(graph)
    report = build_validation_report(graph)

    assert report['summary']['nodes'] > 10
    assert report['summary']['edges'] > 10
    assert report['summary']['excluded_paths'] >= 1
