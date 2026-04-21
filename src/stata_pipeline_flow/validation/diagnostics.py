from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import asdict
from pathlib import Path
import json
import os

from stata_pipeline_flow.model.entities import Diagnostic, GraphModel

SCRIPT_SUFFIXES = ('.do', '.py', '.r', '.R')
KNOWN_ARTIFACT_ROLES = {'reference_input', 'deliverable', 'temporary', 'intermediate', 'generated_artifact', 'artifact', 'placeholder_artifact'}
TERMINAL_OUTPUT_SUFFIXES = {'.png', '.pdf', '.svg', '.csv', '.xlsx', '.ster', '.dot', '.viz'}


def _diagnostic_key(diagnostic: Diagnostic) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    return (
        diagnostic.level,
        diagnostic.code,
        tuple(sorted(diagnostic.payload.items())),
    )


def _append_unique(graph: GraphModel, diagnostic: Diagnostic, seen: set[tuple[str, str, tuple[tuple[str, str], ...]]]) -> None:
    key = _diagnostic_key(diagnostic)
    if key in seen:
        return
    seen.add(key)
    graph.add_diagnostic(diagnostic)


def _build_adjacency(graph: GraphModel) -> tuple[dict[str, list[str]], Counter[str], Counter[str]]:
    adjacency: dict[str, list[str]] = defaultdict(list)
    indegree: Counter[str] = Counter()
    outdegree: Counter[str] = Counter()
    for edge in graph.edges:
        adjacency[edge.source].append(edge.target)
        indegree[edge.target] += 1
        outdegree[edge.source] += 1
    for node_id in graph.nodes:
        adjacency.setdefault(node_id, [])
        indegree.setdefault(node_id, 0)
        outdegree.setdefault(node_id, 0)
    return adjacency, indegree, outdegree


def _find_cycles(graph: GraphModel) -> list[list[str]]:
    adjacency, _, _ = _build_adjacency(graph)
    state: dict[str, int] = {}
    stack: list[str] = []
    stack_index: dict[str, int] = {}
    cycles: list[list[str]] = []
    seen_cycles: set[tuple[str, ...]] = set()

    def canonicalize(cycle: list[str]) -> tuple[str, ...]:
        if not cycle:
            return tuple()
        variants = []
        width = len(cycle)
        for idx in range(width):
            rotated = tuple(cycle[idx:] + cycle[:idx])
            variants.append(rotated)
        reversed_cycle = list(reversed(cycle))
        for idx in range(width):
            rotated = tuple(reversed_cycle[idx:] + reversed_cycle[:idx])
            variants.append(rotated)
        return min(variants)

    def visit(node_id: str) -> None:
        state[node_id] = 1
        stack_index[node_id] = len(stack)
        stack.append(node_id)
        for neighbor in adjacency.get(node_id, []):
            neighbor_state = state.get(neighbor, 0)
            if neighbor_state == 0:
                visit(neighbor)
            elif neighbor_state == 1:
                start = stack_index[neighbor]
                cycle = stack[start:].copy()
                canonical = canonicalize(cycle)
                if canonical and canonical not in seen_cycles:
                    seen_cycles.add(canonical)
                    cycles.append(list(canonical))
        stack.pop()
        stack_index.pop(node_id, None)
        state[node_id] = 2

    for node_id in sorted(graph.nodes):
        if state.get(node_id, 0) == 0:
            visit(node_id)
    return cycles




def _bundle_absolute_path_usage(graph: GraphModel) -> None:
    grouped: dict[str, list[Diagnostic]] = defaultdict(list)
    for diagnostic in graph.diagnostics:
        if diagnostic.code == 'absolute_path_usage' and diagnostic.payload.get('script'):
            grouped[diagnostic.payload['script']].append(diagnostic)

    rebuilt: list[Diagnostic] = []
    emitted_scripts: set[str] = set()

    for diagnostic in graph.diagnostics:
        if diagnostic.code != 'absolute_path_usage':
            rebuilt.append(diagnostic)
            continue

        script = diagnostic.payload.get('script', '')
        members = grouped.get(script)
        if not script or not members:
            rebuilt.append(diagnostic)
            continue
        if script in emitted_scripts:
            continue
        emitted_scripts.add(script)

        if len(members) == 1:
            rebuilt.append(diagnostic)
            continue

        unique_paths: list[str] = []
        seen_paths: set[str] = set()
        for member in members:
            raw_paths = member.payload.get('path', '')
            for part in raw_paths.split(' | '):
                normalized = part.strip()
                if not normalized or normalized in seen_paths:
                    continue
                seen_paths.add(normalized)
                unique_paths.append(normalized)

        payload = {
            'script': script,
            'count': str(len(members)),
            'unique_paths': str(len(unique_paths)),
        }
        sample_paths = ' | '.join(unique_paths[:5])
        if sample_paths:
            payload['sample_paths'] = sample_paths

        rebuilt.append(
            Diagnostic(
                level='warning',
                code='absolute_path_usage',
                message=f'Absolute paths detected {len(members)} times in {script}',
                payload=payload,
            )
        )

    graph.diagnostics = rebuilt

def run_basic_validation(graph: GraphModel) -> GraphModel:
    _bundle_absolute_path_usage(graph)

    artifact_write_edges = [edge for edge in graph.edges if edge.source.endswith(SCRIPT_SUFFIXES) and not edge.target.endswith(SCRIPT_SUFFIXES)]
    artifact_read_edges = [edge for edge in graph.edges if not edge.source.endswith(SCRIPT_SUFFIXES) and edge.target.endswith(SCRIPT_SUFFIXES)]
    writers = Counter(edge.target for edge in artifact_write_edges)
    writers_by_target: dict[str, list[str]] = defaultdict(list)
    for edge in artifact_write_edges:
        writers_by_target[edge.target].append(edge.source)
    readers = Counter(edge.source for edge in artifact_read_edges)
    produced = {edge.target for edge in artifact_write_edges}
    consumed = {edge.source for edge in artifact_read_edges}
    seen = {_diagnostic_key(diagnostic) for diagnostic in graph.diagnostics}

    for target, count in sorted(writers.items()):
        if count > 1:
            writing_scripts = sorted(set(writers_by_target[target]))
            scripts_str = ' | '.join(writing_scripts)
            _append_unique(
                graph,
                Diagnostic(
                    level='warning',
                    code='multiple_writers',
                    message=f'Multiple scripts write the same target ({target}): {scripts_str}',
                    payload={'target': target, 'count': str(count), 'scripts': scripts_str},
                ),
                seen,
            )

    for artifact in sorted(produced - consumed):
        if not artifact.endswith(tuple(sorted(TERMINAL_OUTPUT_SUFFIXES))):
            _append_unique(
                graph,
                Diagnostic(
                    level='info',
                    code='unconsumed_output',
                    message=f'Produced artifact is not consumed downstream: {artifact}',
                    payload={'path': artifact},
                ),
                seen,
            )

    adjacency, indegree, outdegree = _build_adjacency(graph)

    for node_id, node in sorted(graph.nodes.items()):
        if node.node_type in {'artifact', 'artifact_placeholder'} and node_id not in produced and node_id not in consumed:
            _append_unique(
                graph,
                Diagnostic(
                    level='info',
                    code='orphan_artifact',
                    message=f'Orphan artifact node detected: {node_id}',
                    payload={'path': node_id},
                ),
                seen,
            )
        if indegree[node_id] == 0 and outdegree[node_id] == 0:
            _append_unique(
                graph,
                Diagnostic(
                    level='warning',
                    code='orphan_node',
                    message=f'Node has no incoming or outgoing edges: {node_id}',
                    payload={'path': node_id, 'node_type': node.node_type},
                ),
                seen,
            )

    basename_to_nodes: dict[tuple[str, str], list[str]] = defaultdict(list)
    for node_id, node in sorted(graph.nodes.items()):
        basename_to_nodes[(node.node_type, Path(node_id).name)].append(node_id)
        if node.node_type in {'artifact', 'artifact_placeholder'} and (node.role is None or node.role not in KNOWN_ARTIFACT_ROLES):
            _append_unique(
                graph,
                Diagnostic(
                    level='warning',
                    code='unknown_file_role',
                    message=f'Artifact node has an unknown role: {node_id}',
                    payload={'path': node_id, 'role': str(node.role)},
                ),
                seen,
            )

    for (node_type, basename), members in sorted(basename_to_nodes.items()):
        if len(members) > 1:
            _append_unique(
                graph,
                Diagnostic(
                    level='info',
                    code='ambiguous_name',
                    message=f'Multiple {node_type} nodes share the same file name: {basename}',
                    payload={'name': basename, 'node_type': node_type, 'paths': ' | '.join(sorted(members))},
                ),
                seen,
            )

    root = Path(graph.project_root)
    for node_id, node in sorted(graph.nodes.items()):
        if node.path is None:
            continue
        if os.path.isabs(node.path):
            continue
        expected_path = root / node.path
        if node.node_type in {'artifact', 'artifact_placeholder'} and indegree[node_id] > 0 and outdegree[node_id] == 0:
            continue
        if not expected_path.exists():
            _append_unique(
                graph,
                Diagnostic(
                    level='warning',
                    code='missing_referenced_file',
                    message=f'Referenced path does not exist in project tree: {node.path}',
                    payload={'path': node.path, 'node_type': node.node_type},
                ),
                seen,
            )

    cycles = _find_cycles(graph)
    for cycle in cycles:
        cycle_path = ' -> '.join(cycle + [cycle[0]])
        _append_unique(
            graph,
            Diagnostic(
                level='warning',
                code='cycle_detected',
                message=f'Cycle detected: {cycle_path}',
                payload={'cycle': cycle_path},
            ),
            seen,
        )

    if graph.excluded_paths:
        _append_unique(
            graph,
            Diagnostic(
                level='info',
                code='excluded_path_inventory',
                message=f'{len(graph.excluded_paths)} excluded paths recorded in this run.',
                payload={'count': str(len(graph.excluded_paths))},
            ),
            seen,
        )

    if not graph.edges:
        _append_unique(
            graph,
            Diagnostic(level='warning', code='empty_graph', message='Graph has no edges.'),
            seen,
        )

    return graph


def build_validation_report(graph: GraphModel) -> dict[str, object]:
    by_level = Counter(diagnostic.level for diagnostic in graph.diagnostics)
    by_code = Counter(diagnostic.code for diagnostic in graph.diagnostics)
    return {
        'project_root': graph.project_root,
        'summary': {
            'nodes': len(graph.nodes),
            'edges': len(graph.edges),
            'diagnostics': len(graph.diagnostics),
            'by_level': dict(sorted(by_level.items())),
            'by_code': dict(sorted(by_code.items())),
            'excluded_paths': len(graph.excluded_paths),
        },
        'excluded_paths': sorted(set(graph.excluded_paths)),
        'diagnostics': [asdict(diagnostic) for diagnostic in graph.diagnostics],
    }


def write_validation_report(graph: GraphModel, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(build_validation_report(graph), indent=2, sort_keys=True), encoding='utf-8')
    return output_path
