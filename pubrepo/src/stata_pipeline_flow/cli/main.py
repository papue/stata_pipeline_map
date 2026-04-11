from __future__ import annotations

import argparse
import shutil
import subprocess
from dataclasses import replace
from pathlib import Path

from stata_pipeline_flow.config.export import write_cluster_export
from stata_pipeline_flow.config.schema import AppConfig, load_config, sanitize_config
from stata_pipeline_flow.parser.stata_extract import write_edge_csv
from stata_pipeline_flow.render.dot import render_dot
from stata_pipeline_flow.render.json_snapshot import write_snapshot_json
from stata_pipeline_flow.rules.pipeline import PipelineBuilder
from stata_pipeline_flow.validation.diagnostics import run_basic_validation, write_validation_report


def _diagnostic_count(graph, code: str) -> int:
    return sum(1 for diagnostic in graph.diagnostics if diagnostic.code == code)


def _diagnostic_payload_total(graph, code: str, payload_key: str = 'count') -> int:
    total = 0
    for diagnostic in graph.diagnostics:
        if diagnostic.code != code:
            continue
        try:
            total += int(diagnostic.payload.get(payload_key, '0'))
        except (TypeError, ValueError):
            continue
    return total


def _print_config_effects(graph, config: AppConfig) -> None:
    print('Config effects:')
    print(f'- View: {config.display.view}')
    print(f'- Excluded paths: {len(graph.excluded_paths)}')
    if config.exclusions.presets:
        print(f"- Exclusion presets: {','.join(config.exclusions.presets)}")
    exclusion_warning = next((d for d in graph.diagnostics if d.code == 'exclusion_defaults_not_inherited'), None)
    if exclusion_warning:
        print(f'- Exclusion note: {exclusion_warning.message}')
    resolved_families = _diagnostic_count(graph, 'version_family_resolved')
    if resolved_families:
        print(f'- Version families collapsed: {resolved_families}')
    hidden_temp = _diagnostic_payload_total(graph, 'temporary_outputs_hidden')
    if hidden_temp:
        print(f'- Temporary outputs hidden: {hidden_temp}')
    shown_temp = _diagnostic_payload_total(graph, 'temporary_outputs_rendered')
    if shown_temp:
        erased_shown = _diagnostic_payload_total(graph, 'temporary_outputs_rendered', 'erased_count')
        suffix = f' ({erased_shown} erased temp artifacts)' if erased_shown else ''
        print(f'- Temporary outputs shown: {shown_temp}{suffix}')
    irrelevant = [diagnostic for diagnostic in graph.diagnostics if diagnostic.code == 'display_option_irrelevant']
    if irrelevant:
        print(f'- View-specific setting notices: {len(irrelevant)}')
        for diagnostic in irrelevant[:3]:
            print(f'  * {diagnostic.message}')


def resolve_config(args: argparse.Namespace) -> AppConfig:
    if args.config:
        config = load_config(Path(args.config))
    else:
        config = AppConfig(project_root=str(Path(args.project_root or '.').resolve()))
    if getattr(args, 'project_root', None):
        config.project_root = str(Path(args.project_root).resolve())
    if getattr(args, 'edge_csv', None):
        config.parser.edge_csv_path = args.edge_csv
    return sanitize_config(config)


def build_graph(config: AppConfig):
    graph = PipelineBuilder(config).build(Path(config.project_root))
    graph = run_basic_validation(graph)
    return graph


def command_summary(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    graph = build_graph(config)
    script_nodes = sum(1 for node in graph.nodes.values() if node.node_type == 'script')
    artifact_nodes = sum(1 for node in graph.nodes.values() if node.node_type == 'artifact')
    print(f'Project root: {config.project_root}')
    print(f'Nodes: {len(graph.nodes)} (scripts={script_nodes}, artifacts={artifact_nodes})')
    print(f'Edges: {len(graph.edges)}')
    print(f'Clusters: {len(graph.clusters)}')
    print(f'Diagnostics: {len(graph.diagnostics)}')
    _print_config_effects(graph, config)
    for diagnostic in graph.diagnostics:
        print(f'- [{diagnostic.level}] {diagnostic.code}: {diagnostic.message}')
    return 0




def _render_dot_text(config: AppConfig, show_edge_labels: bool = False):
    graph = build_graph(config)
    dot = render_dot(
        graph,
        show_edge_labels=show_edge_labels or config.display.show_edge_labels,
        display=config.display,
        layout=config.layout,
    )
    return graph, dot

def command_extract_edges(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    if getattr(args, 'output', None):
        config.parser.edge_csv_path = args.output
    graph = build_graph(config)
    output_path = Path(config.project_root) / config.parser.edge_csv_path
    write_edge_csv(graph, output_path)
    print(f'Wrote edge CSV to {output_path}')
    return 0


def command_render_dot(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    graph, dot = _render_dot_text(config, show_edge_labels=args.show_edge_labels)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(dot, encoding='utf-8')
    print(f'Wrote DOT to {output_path}')
    _print_config_effects(graph, config)
    return 0




def command_render_image(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    graph, dot = _render_dot_text(config, show_edge_labels=args.show_edge_labels)

    dot_executable = shutil.which('dot')
    if not dot_executable:
        print('Graphviz was not found on PATH. Install Graphviz and make sure the "dot" command works in your terminal.', flush=True)
        print('You can still use render-dot to create a .dot file and render it later once Graphviz is installed.', flush=True)
        return 2

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    completed = subprocess.run(
        [dot_executable, f'-T{args.format}', '-o', str(output_path)],
        input=dot,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        stderr = completed.stderr.strip() or 'Graphviz failed to render the image.'
        print(stderr, flush=True)
        return completed.returncode

    if getattr(args, 'dot_output', None):
        dot_output = Path(args.dot_output)
        dot_output.parent.mkdir(parents=True, exist_ok=True)
        dot_output.write_text(dot, encoding='utf-8')
        print(f'Wrote DOT to {dot_output}')

    print(f'Wrote {args.format.upper()} to {output_path}')
    _print_config_effects(graph, config)
    return 0


def build_graph_for_cluster_export(config: AppConfig, mode: str):
    export_config = config if mode == 'resolved' else replace(config, clusters=[])
    return build_graph(export_config)



def command_export_clusters(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    graph = build_graph_for_cluster_export(config, args.mode)
    output_path = Path(args.output)
    write_cluster_export(graph, output_path)
    print(f'Wrote cluster starter config to {output_path}')
    print(f'Export mode: {args.mode}')
    print(f'Exported clusters: {sum(1 for cluster in graph.sorted_clusters() if any(graph.nodes[node_id].node_type == "script" for node_id in cluster.node_ids if node_id in graph.nodes))}')
    return 0



def command_snapshot_json(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    graph = build_graph(config)
    output_path = Path(args.output)
    write_snapshot_json(graph, output_path, display=config.display, layout=config.layout)
    print(f'Wrote JSON snapshot to {output_path}')
    return 0

def command_validate(args: argparse.Namespace) -> int:
    config = resolve_config(args)
    graph = build_graph(config)
    output_path = Path(args.output)
    write_validation_report(graph, output_path)
    print(f'Wrote validation report to {output_path}')
    print(f'Diagnostics: {len(graph.diagnostics)}')
    _print_config_effects(graph, config)
    for diagnostic in graph.diagnostics:
        print(f'- [{diagnostic.level}] {diagnostic.code}: {diagnostic.message}')
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='stata-pipeline-flow')
    subparsers = parser.add_subparsers(dest='command', required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument('--project-root', default='.')
    common.add_argument('--config')
    common.add_argument('--edge-csv', default='viewer_output/parser_edges.csv')

    summary = subparsers.add_parser('summary', help='Print a graph summary.', parents=[common])
    summary.set_defaults(func=command_summary)

    extract = subparsers.add_parser('extract-edges', help='Extract lineage edges from Stata scripts.', parents=[common])
    extract.add_argument('--output', help='Optional alias for --edge-csv for consistency with other write commands.')
    extract.set_defaults(func=command_extract_edges)

    render = subparsers.add_parser('render-dot', help='Render DOT from the graph model.', parents=[common])
    render_image = subparsers.add_parser('render-image', help='Render a final image directly via Graphviz.', parents=[common])
    snapshot = subparsers.add_parser('snapshot-json', help='Write a stable JSON graph snapshot.', parents=[common])
    snapshot.add_argument('--output', default='viewer_output/graph_snapshot.json')
    snapshot.set_defaults(func=command_snapshot_json)

    render.add_argument('--output', required=True)
    render.add_argument('--show-edge-labels', action='store_true')
    render.set_defaults(func=command_render_dot)

    render_image.add_argument('--output', required=True)
    render_image.add_argument('--format', choices=['png', 'svg', 'pdf'], default='png')
    render_image.add_argument('--dot-output', help='Optional path to also save the intermediate DOT file.')
    render_image.add_argument('--show-edge-labels', action='store_true')
    render_image.set_defaults(func=command_render_image)

    validate = subparsers.add_parser('validate', help='Run validation and write a structured report.', parents=[common])
    validate.add_argument('--output', default='viewer_output/validation_report.json')
    validate.set_defaults(func=command_validate)

    export_clusters = subparsers.add_parser('export-clusters', help='Export inferred or resolved clusters as an editable YAML starter config.', parents=[common])
    export_clusters.add_argument('--output', default='viewer_output/cluster_starter.yaml')
    export_clusters.add_argument('--mode', choices=['auto', 'resolved'], default='auto')
    export_clusters.set_defaults(func=command_export_clusters)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == '__main__':
    raise SystemExit(main())
