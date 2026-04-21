from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import json

from stata_pipeline_flow.config.schema import DisplayConfig, LayoutConfig
from stata_pipeline_flow.model.entities import Cluster, Edge, GraphModel, Node


def _node_payload(node: Node) -> dict[str, object]:
    return {
        'node_id': node.node_id,
        'label': node.label,
        'node_type': node.node_type,
        'path': node.path,
        'role': node.role,
        'cluster_id': node.cluster_id,
        'metadata': dict(sorted(node.metadata.items())),
    }


def _edge_payload(edge: Edge) -> dict[str, object]:
    return {
        'source': edge.source,
        'target': edge.target,
        'operation': edge.operation,
        'kind': edge.kind,
        'visible_label': edge.visible_label,
        'metadata': dict(sorted(edge.metadata.items())),
    }


def _cluster_payload(cluster: Cluster) -> dict[str, object]:
    return {
        'cluster_id': cluster.cluster_id,
        'label': cluster.label,
        'node_ids': sorted(cluster.node_ids),
        'metadata': dict(sorted(cluster.metadata.items())),
    }


def build_snapshot(graph: GraphModel, display: DisplayConfig | None = None, layout: LayoutConfig | None = None) -> dict[str, object]:
    display = display or DisplayConfig()
    layout = layout or LayoutConfig()
    return {
        'project_root': graph.project_root,
        'metadata': dict(sorted(graph.metadata.items())),
        'config': {
            'display': asdict(display),
            'layout': {
                'rankdir': layout.rankdir,
                'unclustered_artifacts_position': layout.unclustered_artifacts_position,
            },
        },
        'nodes': [_node_payload(node) for node in graph.sorted_nodes()],
        'edges': [_edge_payload(edge) for edge in graph.edges],
        'clusters': [_cluster_payload(cluster) for cluster in graph.sorted_clusters()],
        'diagnostics': [
            {
                'level': diagnostic.level,
                'code': diagnostic.code,
                'message': diagnostic.message,
                'payload': dict(sorted(diagnostic.payload.items())),
            }
            for diagnostic in graph.diagnostics
        ],
        'excluded_paths': sorted(graph.excluded_paths),
    }


def write_snapshot_json(graph: GraphModel, output_path: Path, display: DisplayConfig | None = None, layout: LayoutConfig | None = None) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = build_snapshot(graph, display=display, layout=layout)
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=False) + '\n', encoding='utf-8')
