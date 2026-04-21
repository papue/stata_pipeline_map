from __future__ import annotations

from pathlib import Path

from data_pipeline_flow.config.schema import load_config
from data_pipeline_flow.rules.pipeline import PipelineBuilder
from data_pipeline_flow.validation.diagnostics import run_basic_validation

from conftest import GOLDEN_ROOT, normalize_project_root_text, read_json, read_text, run_cli


def _graph_snapshot(project_root: Path) -> dict[str, object]:
    config = load_config(project_root / 'config_manual.yaml')
    config.project_root = str(project_root)
    graph = PipelineBuilder(config).build(project_root)
    graph = run_basic_validation(graph)
    return {
        'nodes': [
            {
                'id': node.node_id,
                'type': node.node_type,
                'role': node.role,
                'cluster_id': node.cluster_id,
            }
            for node in graph.sorted_nodes()
        ],
        'edges': [
            {
                'source': edge.source,
                'target': edge.target,
                'operation': edge.operation,
                'kind': edge.kind,
            }
            for edge in graph.edges
        ],
        'clusters': [
            {
                'id': cluster.cluster_id,
                'label': cluster.label,
                'node_ids': sorted(cluster.node_ids),
                'kind': cluster.metadata.get('kind'),
                'order': cluster.metadata.get('order'),
            }
            for cluster in graph.sorted_clusters()
        ],
        'diagnostics': [
            {
                'level': diagnostic.level,
                'code': diagnostic.code,
                'payload': diagnostic.payload,
            }
            for diagnostic in graph.diagnostics
        ],
        'excluded_paths': sorted(set(graph.excluded_paths)),
    }



def test_fixture_graph_snapshot_matches_golden(regression_project_root: Path) -> None:
    assert _graph_snapshot(regression_project_root) == read_json(GOLDEN_ROOT / 'graph_snapshot.json')



def test_summary_cli_matches_golden(regression_project_root: Path) -> None:
    result = run_cli(
        'summary',
        '--project-root',
        str(regression_project_root),
        '--config',
        str(regression_project_root / 'config_manual.yaml'),
    )

    assert result.returncode == 0, result.stderr
    normalized_stdout = normalize_project_root_text(result.stdout, regression_project_root)
    assert normalized_stdout == read_text(GOLDEN_ROOT / 'summary.txt')



def test_extract_edges_cli_matches_golden_csv(regression_project_root: Path) -> None:
    result = run_cli('extract-edges', '--project-root', str(regression_project_root))

    assert result.returncode == 0, result.stderr
    assert 'Wrote edge CSV' in result.stdout
    assert read_text(regression_project_root / 'viewer_output' / 'parser_edges.csv') == read_text(GOLDEN_ROOT / 'parser_edges.csv')



def test_extract_edges_cli_accepts_output_alias(regression_project_root: Path) -> None:
    output_path = regression_project_root / 'viewer_output' / 'parser_edges_alias.csv'
    result = run_cli(
        'extract-edges',
        '--project-root',
        str(regression_project_root),
        '--output',
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    assert f'Wrote edge CSV to {output_path}' in result.stdout
    assert read_text(output_path) == read_text(GOLDEN_ROOT / 'parser_edges.csv')



def test_render_dot_cli_matches_golden_and_hides_labels(regression_project_root: Path) -> None:
    output_path = regression_project_root / 'viewer_output' / 'fixture.dot'
    result = run_cli(
        'render-dot',
        '--project-root',
        str(regression_project_root),
        '--config',
        str(regression_project_root / 'config_manual.yaml'),
        '--output',
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    rendered = read_text(output_path)
    assert rendered == read_text(GOLDEN_ROOT / 'rendered.dot')
    assert 'label="merge"' not in rendered
    assert 'label="append"' not in rendered
    assert 'label="save"' not in rendered



def test_render_dot_cli_can_show_edge_labels(regression_project_root: Path) -> None:
    output_path = regression_project_root / 'viewer_output' / 'fixture_labels.dot'
    result = run_cli(
        'render-dot',
        '--project-root',
        str(regression_project_root),
        '--output',
        str(output_path),
        '--show-edge-labels',
    )

    assert result.returncode == 0, result.stderr
    rendered = read_text(output_path)
    assert 'label="merge"' in rendered
    assert 'label="import"' in rendered
    assert 'label="save"' in rendered



def test_validate_cli_matches_golden_report(regression_project_root: Path) -> None:
    output_path = regression_project_root / 'viewer_output' / 'validation_report.json'
    result = run_cli(
        'validate',
        '--project-root',
        str(regression_project_root),
        '--config',
        str(regression_project_root / 'config_manual.yaml'),
        '--output',
        str(output_path),
    )

    assert result.returncode == 0, result.stderr
    assert 'Diagnostics: 9' in result.stdout
    report = read_json(output_path)
    report['project_root'] = '<PROJECT_ROOT>'
    assert report == read_json(GOLDEN_ROOT / 'validation_report.json')



def test_export_clusters_cli_matches_golden_outputs(regression_project_root: Path) -> None:
    auto_output = regression_project_root / 'viewer_output' / 'clusters_auto.yaml'
    resolved_output = regression_project_root / 'viewer_output' / 'clusters_resolved.yaml'

    auto_result = run_cli(
        'export-clusters',
        '--project-root',
        str(regression_project_root),
        '--config',
        str(regression_project_root / 'config_manual.yaml'),
        '--mode',
        'auto',
        '--output',
        str(auto_output),
    )
    resolved_result = run_cli(
        'export-clusters',
        '--project-root',
        str(regression_project_root),
        '--config',
        str(regression_project_root / 'config_manual.yaml'),
        '--mode',
        'resolved',
        '--output',
        str(resolved_output),
    )

    assert auto_result.returncode == 0, auto_result.stderr
    assert resolved_result.returncode == 0, resolved_result.stderr
    assert read_text(auto_output) == read_text(GOLDEN_ROOT / 'export_auto.yaml')
    assert read_text(resolved_output) == read_text(GOLDEN_ROOT / 'export_resolved.yaml')
