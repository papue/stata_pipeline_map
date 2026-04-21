from __future__ import annotations

from pathlib import PurePosixPath

from stata_pipeline_flow.config.schema import AppConfig
from stata_pipeline_flow.model.entities import Diagnostic, Edge, GraphModel, Node


_SCRIPT_TYPES = {'script', 'script_placeholder'}

_SCRIPT_EXTENSIONS = {'.do', '.py', '.r', '.R'}


def _infer_edge_kind(src: Node, tgt: Node) -> str:
    s = src.node_type in _SCRIPT_TYPES
    t = tgt.node_type in _SCRIPT_TYPES
    if s and not t:
        return 'script_to_artifact'
    if not s and t:
        return 'artifact_to_script'
    if s and t:
        return 'script_to_script'
    return 'artifact_to_artifact'


def _placeholder_node_type(node_id: str) -> tuple[str, str]:
    """Return (node_type, role) for a placeholder node based on file extension."""
    suffix = PurePosixPath(node_id).suffix
    if suffix in _SCRIPT_EXTENSIONS:
        return 'script_placeholder', 'placeholder_script'
    return 'artifact_placeholder', 'placeholder_artifact'


def _make_placeholder_node(node_id: str) -> Node:
    node_type, role = _placeholder_node_type(node_id)
    return Node(
        node_id=node_id,
        label=PurePosixPath(node_id).name,
        node_type=node_type,
        path=None,
        role=role,
        cluster_id=None,
        metadata={'source': 'manual_edge'},
    )


def _normalize_path(raw: str) -> str:
    """Normalize a manual-edge path to match the forward-slash node IDs used in the graph.

    Converts backslashes to forward slashes and strips a leading ``./``.
    """
    normalized = raw.replace('\\', '/')
    if normalized.startswith('./'):
        normalized = normalized[2:]
    return normalized


def apply_manual_edges(graph: GraphModel, config: AppConfig) -> GraphModel:
    if not config.manual_edges:
        return graph

    existing_pairs: set[tuple[str, str]] = {
        (edge.source, edge.target) for edge in graph.edges
    }

    applied = 0
    skipped = 0
    total = len(config.manual_edges)

    for index, entry in enumerate(config.manual_edges, start=1):
        # Validate required fields
        if not entry.source or not entry.target:
            graph.add_diagnostic(Diagnostic(
                level='warning',
                code='invalid_manual_edge',
                message=f'Manual edge entry #{index} has a blank source or target and will be skipped.',
                payload={
                    'entry_index': str(index),
                    'source': entry.source,
                    'target': entry.target,
                },
            ))
            skipped += 1
            continue

        # Normalize paths: backslashes → forward slashes, strip leading ./
        source = _normalize_path(entry.source)
        target = _normalize_path(entry.target)

        # Duplicate check
        if (source, target) in existing_pairs:
            graph.add_diagnostic(Diagnostic(
                level='info',
                code='manual_edge_duplicate',
                message=f'Manual edge {source!r} -> {target!r} already exists in the graph and will be skipped.',
                payload={
                    'source': source,
                    'target': target,
                },
            ))
            skipped += 1
            continue

        # Node lookup
        src_node = graph.nodes.get(source)
        tgt_node = graph.nodes.get(target)

        if entry.on_missing == 'placeholder':
            # Inject placeholder nodes for any that are missing
            for missing_id, current_node in ((source, src_node), (target, tgt_node)):
                if current_node is None:
                    graph.add_node(_make_placeholder_node(missing_id))
                    graph.add_diagnostic(Diagnostic(
                        level='info',
                        code='manual_edge_placeholder_injected',
                        message=f'Placeholder node injected for {missing_id!r} (referenced in manual edge #{index}).',
                        payload={
                            'node_id': missing_id,
                            'source': source,
                            'target': target,
                        },
                    ))
            # Re-fetch both nodes after potential injection
            src_node = graph.nodes.get(source)
            tgt_node = graph.nodes.get(target)
        else:
            # on_missing == 'warn': emit warning for each missing node and skip
            missing = False
            for missing_id, current_node in ((source, src_node), (target, tgt_node)):
                if current_node is None:
                    graph.add_diagnostic(Diagnostic(
                        level='warning',
                        code='manual_edge_node_not_found',
                        message=f'Manual edge #{index} references node {missing_id!r} which does not exist in the graph.',
                        payload={
                            'node_id': missing_id,
                            'source': source,
                            'target': target,
                            'entry_index': str(index),
                        },
                    ))
                    missing = True
            if missing:
                skipped += 1
                continue

        # Add the edge
        assert src_node is not None
        assert tgt_node is not None
        graph.add_edge(Edge(
            source=source,
            target=target,
            operation='manual',
            kind=_infer_edge_kind(src_node, tgt_node),
            visible_label=entry.label,
        ))
        existing_pairs.add((source, target))
        applied += 1

    graph.add_diagnostic(Diagnostic(
        level='info',
        code='manual_edges_applied',
        message=f'Manual edges: {applied} applied, {skipped} skipped, {total} total.',
        payload={
            'applied': str(applied),
            'skipped': str(skipped),
            'total': str(total),
        },
    ))
    return graph
