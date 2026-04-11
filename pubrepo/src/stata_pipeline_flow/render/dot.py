from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

from stata_pipeline_flow.config.schema import DisplayConfig, LayoutConfig
from stata_pipeline_flow.model.entities import Cluster, GraphModel, Node

_BASE_NODE_STYLE = {
    'script': 'shape=box, style="rounded,filled", margin="0.10,0.06"',
    'artifact': 'shape=ellipse',
    'artifact_placeholder': 'shape=ellipse, style="dashed"',
}

_THEME_BUNDLES = {
    'modern-light': {
        'graph': 'pad=0.2, nodesep=0.35, ranksep=0.6, splines=true',
        'node': 'fontsize=10',
        'edge': 'fontsize=9',
        'cluster_style': 'rounded',
        'script_fill': 'fillcolor="#EEF3FF"',
        'deliverable_fill': 'fillcolor="#FFF3D6"',
    },
    'modern-dark': {
        'graph': 'pad=0.2, nodesep=0.35, ranksep=0.6, splines=true, bgcolor="#1E1F24", fontcolor="#F5F5F5"',
        'node': 'fontsize=10, fontcolor="#F5F5F5", color="#BFC7D5"',
        'edge': 'fontsize=9, fontcolor="#E5E7EB", color="#9CA3AF"',
        'cluster_style': 'rounded',
        'script_fill': 'fillcolor="#2F3B52"',
        'deliverable_fill': 'fillcolor="#5A4728"',
    },
    'warm-neutral': {
        'graph': 'pad=0.2, nodesep=0.35, ranksep=0.6, splines=true',
        'node': 'fontsize=10',
        'edge': 'fontsize=9',
        'cluster_style': 'rounded',
        'script_fill': 'fillcolor="#F5EBDD"',
        'deliverable_fill': 'fillcolor="#F7DDBA"',
    },
}


def _view_mode(display: DisplayConfig) -> str:
    return display.view or display.mode or 'overview'


def _label_source(node: Node) -> str:
    return node.path or node.node_id


def _format_label(node: Node, display: DisplayConfig) -> str:
    value = _label_source(node)
    path = PurePosixPath(value)

    if display.node_label_style == 'full_path':
        label = value
    elif display.node_label_style == 'stem':
        label = path.stem
    else:
        depth = max(0, int(display.label_path_depth))
        parts = list(path.parts)
        if parts:
            parts = parts[-(depth + 1):]
        label = '/'.join(parts) if parts else value

    if not display.show_extensions and display.node_label_style != 'full_path':
        label_path = PurePosixPath(label)
        parts = list(label_path.parts)
        if parts:
            parts[-1] = PurePosixPath(parts[-1]).stem
            label = '/'.join(parts)
    return label


def _node_attr_string(node: Node, display: DisplayConfig, theme: dict[str, str]) -> str:
    attrs: list[str] = [_BASE_NODE_STYLE.get(node.node_type, 'shape=ellipse')]
    if node.node_type == 'script':
        attrs.append(theme['script_fill'])
    if node.role == 'deliverable' and node.node_type == 'artifact':
        attrs.append('style="filled"')
        attrs.append(theme['deliverable_fill'])
    if node.role == 'temporary' and node.node_type == 'artifact':
        if node.metadata.get('erased') == 'true':
            attrs.append('style="dashed"')
            attrs.append('penwidth=2')
        else:
            attrs.append('style="dashed"')
    if node.node_type == 'artifact_placeholder':
        if display.placeholder_style == 'filled_dashed':
            attrs.append('style="dashed,filled"')
            attrs.append(theme['deliverable_fill'])
        elif display.placeholder_style == 'bold':
            attrs.append('penwidth=2')
        else:
            attrs.append('style="dashed"')
    attrs.append(f'label="{_format_label(node, display)}"')
    return ', '.join(attrs)


def _cluster_summary_attr_string(cluster: Cluster, theme: dict[str, str]) -> str:
    label = cluster.label or cluster.cluster_id
    return ', '.join([
        'shape=box',
        'style="rounded,filled"',
        'margin="0.10,0.06"',
        theme['script_fill'],
        f'label="{label}"',
    ])


def _resolve_theme(name: str) -> dict[str, str]:
    return _THEME_BUNDLES.get(name, _THEME_BUNDLES['modern-light'])


def _should_show_node(node: Node, display: DisplayConfig) -> bool:
    view = _view_mode(display)
    if view == 'deliverables':
        return node.node_type == 'script' or node.role in {'deliverable', 'placeholder_artifact', 'reference_input'}
    if view == 'scripts_only':
        return node.node_type == 'script'
    if view == 'stage_overview':
        return node.node_type == 'script' and not node.cluster_id
    return True


def render_dot(
    graph: GraphModel,
    show_edge_labels: bool = False,
    display: DisplayConfig | None = None,
    layout: LayoutConfig | None = None,
) -> str:
    display = display or DisplayConfig()
    layout = layout or LayoutConfig(rankdir=graph.metadata.get('rankdir', 'LR'))
    theme = _resolve_theme(display.theme)
    rankdir = graph.metadata.get('rankdir', layout.rankdir or 'LR')
    view = _view_mode(display)
    stage_overview = view == 'stage_overview'

    lines = [
        'digraph pipeline {',
        f'  rankdir={rankdir};',
        f'  graph [{theme["graph"]}];',
        f'  node [{theme["node"]}];',
        f'  edge [{theme["edge"]}];',
    ]

    visible_nodes = {node.node_id for node in graph.sorted_nodes() if _should_show_node(node, display)}
    clustered_node_ids: set[str] = set()
    collapsed_cluster_ids = {
        cluster.cluster_id
        for cluster in graph.sorted_clusters()
        if cluster.metadata.get('collapse') == 'true' or stage_overview
    }
    rendered_aliases: dict[str, str] = {}
    lane_groups: dict[str, list[str]] = defaultdict(list)

    for cluster in graph.sorted_clusters():
        member_ids = [node_id for node_id in cluster.node_ids if node_id in graph.nodes]
        if not member_ids:
            continue

        if stage_overview:
            member_ids = [node_id for node_id in member_ids if graph.nodes[node_id].node_type == 'script']
            if not member_ids:
                continue
            summary_id = f'cluster::{cluster.cluster_id}'
            lines.append(f'  "{summary_id}" [{_cluster_summary_attr_string(cluster, theme)}];')
            for node_id in member_ids:
                rendered_aliases[node_id] = summary_id
            clustered_node_ids.update(member_ids)
            lane = cluster.metadata.get('lane')
            if lane:
                lane_groups[lane].append(summary_id)
            continue

        member_ids = [node_id for node_id in member_ids if node_id in visible_nodes]
        if not member_ids:
            continue
        lane = cluster.metadata.get('lane')
        if cluster.cluster_id in collapsed_cluster_ids:
            summary_id = f'cluster::{cluster.cluster_id}'
            lines.append(f'  "{summary_id}" [{_cluster_summary_attr_string(cluster, theme)}];')
            for node_id in member_ids:
                rendered_aliases[node_id] = summary_id
            clustered_node_ids.update(member_ids)
            if lane:
                lane_groups[lane].append(summary_id)
            continue

        clustered_node_ids.update(member_ids)
        lines.append(f'  subgraph "{cluster.cluster_id}" {{')
        label = cluster.label or cluster.cluster_id
        lines.append(f'    label="{label}";')
        lines.append(f'    style="{theme["cluster_style"]}";')
        for node_id in sorted(member_ids):
            node = graph.nodes[node_id]
            lines.append(f'    "{node.node_id}" [{_node_attr_string(node, display, theme)}];')
            rendered_aliases[node_id] = node.node_id
        lines.append('  }')
        if lane:
            lane_groups[lane].extend(sorted(member_ids))

    unclustered_artifacts: list[str] = []
    for node in graph.sorted_nodes():
        if node.node_id not in visible_nodes or node.node_id in clustered_node_ids:
            continue
        lines.append(f'  "{node.node_id}" [{_node_attr_string(node, display, theme)}];')
        rendered_aliases[node.node_id] = node.node_id
        if node.node_type != 'script':
            unclustered_artifacts.append(node.node_id)

    for lane, node_ids in sorted(lane_groups.items()):
        unique_node_ids = []
        seen: set[str] = set()
        for node_id in node_ids:
            if node_id in seen:
                continue
            seen.add(node_id)
            unique_node_ids.append(node_id)
        if len(unique_node_ids) < 2:
            continue
        lines.append(f'  subgraph "lane::{lane}" {{')
        lines.append('    rank="same";')
        for node_id in unique_node_ids:
            lines.append(f'    "{node_id}";')
        lines.append('  }')

    artifact_position = graph.metadata.get('unclustered_artifacts_position', layout.unclustered_artifacts_position or 'auto')
    if unclustered_artifacts and artifact_position in {'left', 'right', 'separate_lane'}:
        lines.append('  subgraph "position::unclustered_artifacts" {')
        if artifact_position == 'left':
            lines.append('    rank="min";')
        elif artifact_position == 'right':
            lines.append('    rank="max";')
        else:
            lines.append('    rank="same";')
        for node_id in unclustered_artifacts:
            lines.append(f'    "{node_id}";')
        lines.append('  }')

    effective_edge_labels = show_edge_labels
    if display.edge_label_mode in {'show', 'operation'}:
        effective_edge_labels = True
    elif display.edge_label_mode == 'hidden':
        effective_edge_labels = False

    bridge_edges: set[tuple[str, str]] = set()
    aliased_node_ids = set(rendered_aliases)
    hidden_node_ids = sorted(set(graph.nodes) - aliased_node_ids)
    for hidden_id in hidden_node_ids:
        incoming_aliases: set[str] = set()
        outgoing_aliases: set[str] = set()
        for edge in graph.edges:
            if edge.target == hidden_id and edge.source in rendered_aliases:
                incoming_aliases.add(rendered_aliases[edge.source])
            elif edge.source == hidden_id and edge.target in rendered_aliases:
                outgoing_aliases.add(rendered_aliases[edge.target])
        for source_id in incoming_aliases:
            for target_id in outgoing_aliases:
                if source_id != target_id:
                    bridge_edges.add((source_id, target_id))

    for node in graph.sorted_nodes():
        if node.node_type == 'script':
            continue
        incoming_aliases: set[str] = set()
        outgoing_aliases: set[str] = set()
        for edge in graph.edges:
            if edge.target == node.node_id and edge.source in rendered_aliases:
                incoming_aliases.add(rendered_aliases[edge.source])
            elif edge.source == node.node_id and edge.target in rendered_aliases:
                outgoing_aliases.add(rendered_aliases[edge.target])
        if not incoming_aliases or not outgoing_aliases:
            continue
        needs_bridge = view in {'scripts_only', 'stage_overview'} or any(
            alias.startswith('cluster::') for alias in incoming_aliases | outgoing_aliases
        )
        if not needs_bridge:
            continue
        for source_id in incoming_aliases:
            for target_id in outgoing_aliases:
                if source_id != target_id:
                    bridge_edges.add((source_id, target_id))

    emitted_edges: set[tuple[str, str, str]] = set()
    for edge in graph.edges:
        if edge.source not in rendered_aliases or edge.target not in rendered_aliases:
            continue
        source_id = rendered_aliases[edge.source]
        target_id = rendered_aliases[edge.target]
        if source_id == target_id:
            continue
        edge_label = edge.visible_label if effective_edge_labels and edge.visible_label else ''
        dedupe_key = (source_id, target_id, edge_label)
        if dedupe_key in emitted_edges:
            continue
        emitted_edges.add(dedupe_key)
        attrs = []
        if edge_label:
            attrs.append(f'label="{edge_label}"')
        attr_block = f' [{", ".join(attrs)}]' if attrs else ''
        lines.append(f'  "{source_id}" -> "{target_id}"{attr_block};')

    for source_id, target_id in sorted(bridge_edges):
        dedupe_key = (source_id, target_id, '')
        if dedupe_key in emitted_edges or source_id == target_id:
            continue
        emitted_edges.add(dedupe_key)
        lines.append(f'  "{source_id}" -> "{target_id}";')

    lines.append('}')
    return '\n'.join(lines)
