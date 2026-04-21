from __future__ import annotations

from pathlib import Path

from stata_pipeline_flow.model.entities import Cluster, GraphModel

SCRIPT_NODE_TYPE = 'script'


def build_cluster_export_document(graph: GraphModel, strategy: str = 'auto') -> str:
    lines: list[str] = [
        '# Generated cluster starter config.',
        '# Edit cluster ids, labels, and script members as needed.',
        '# Artifact memberships are recomputed automatically from script memberships.',
        'project_root: .',
        'clustering:',
        '  enabled: true',
        f'  strategy: {strategy}',
        'clusters:',
    ]

    exported_any = False
    for cluster in graph.sorted_clusters():
        script_members = _script_members(graph, cluster)
        # Only skip if neither direct script members nor child cluster references exist
        if not script_members and not cluster.member_cluster_ids:
            continue
        exported_any = True
        lines.extend(_serialize_cluster(cluster, script_members))

    if not exported_any:
        lines.append('  []')

    return '\n'.join(lines) + '\n'



def write_cluster_export(graph: GraphModel, output_path: Path, strategy: str = 'auto') -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_cluster_export_document(graph, strategy=strategy), encoding='utf-8')
    return output_path



def _serialize_cluster(cluster: Cluster, script_members: list[str]) -> list[str]:
    lines = [f'  - id: {_quote_yaml_string(cluster.cluster_id)}']
    if cluster.label:
        lines.append(f'    label: {_quote_yaml_string(cluster.label)}')
    if cluster.member_cluster_ids:
        lines.append('    member_cluster_ids:')
        for child_id in cluster.member_cluster_ids:
            lines.append(f'      - {_quote_yaml_string(child_id)}')
    else:
        lines.append('    members:')
        for member in script_members:
            lines.append(f'      - {_quote_yaml_string(member)}')
    return lines



def _script_members(graph: GraphModel, cluster: Cluster) -> list[str]:
    members = [
        node_id
        for node_id in cluster.node_ids
        if graph.nodes.get(node_id) is not None and graph.nodes[node_id].node_type == SCRIPT_NODE_TYPE
    ]
    return sorted(members)



def _quote_yaml_string(value: str) -> str:
    escaped = value.replace('\\', '\\\\').replace('"', '\\"')
    return f'"{escaped}"'
