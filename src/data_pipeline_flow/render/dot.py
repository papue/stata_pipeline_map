from __future__ import annotations

from pathlib import PurePosixPath

from data_pipeline_flow.config.schema import DisplayConfig, LayoutConfig
from data_pipeline_flow.model.entities import Cluster, GraphModel, Node

_BASE_NODE_STYLE = {
    'script': 'shape=box, style="rounded,filled", margin="0.10,0.06"',
    'artifact': 'shape=ellipse',
    'artifact_placeholder': 'shape=ellipse, style="dashed"',
    'script_placeholder': 'shape=box, style="rounded,dashed,filled", margin="0.10,0.06"',
}

_THEME_BUNDLES = {
    'modern-light': {
        'graph': 'pad=0.2, nodesep=0.35, ranksep=0.6, splines=true',
        'node': 'fontsize=10',
        'edge': 'fontsize=9',
        'cluster_style': 'rounded',
        'cluster_bgcolor': 'transparent',
        'cluster_color': '#4A5568',
        'script_fill':  'fillcolor="#EEF3FF"',  # stata (default)
        'python_fill':  'fillcolor="#EEFAF0"',  # light green
        'r_fill':       'fillcolor="#FFF0EE"',  # light salmon
        'deliverable_fill': 'fillcolor="#FFF3D6"',
    },
    'modern-dark': {
        'graph': 'pad=0.2, nodesep=0.35, ranksep=0.6, splines=true, bgcolor="#1E1F24", fontcolor="#F5F5F5"',
        'node': 'fontsize=10, fontcolor="#F5F5F5", color="#BFC7D5"',
        'edge': 'fontsize=9, fontcolor="#E5E7EB", color="#9CA3AF"',
        'cluster_style': 'rounded',
        'cluster_bgcolor': 'transparent',
        'cluster_color': '#BFC7D5',
        'script_fill':  'fillcolor="#2F3B52"',  # stata (default)
        'python_fill':  'fillcolor="#1E3A2F"',  # dark green
        'r_fill':       'fillcolor="#3A2020"',  # dark salmon
        'deliverable_fill': 'fillcolor="#5A4728"',
    },
    'warm-neutral': {
        'graph': 'pad=0.2, nodesep=0.35, ranksep=0.6, splines=true',
        'node': 'fontsize=10',
        'edge': 'fontsize=9',
        'cluster_style': 'rounded',
        'cluster_bgcolor': 'transparent',
        'cluster_color': '#7A6555',
        'script_fill':  'fillcolor="#F5EBDD"',  # stata (default)
        'python_fill':  'fillcolor="#E8F5E8"',  # warm green
        'r_fill':       'fillcolor="#F5E8E8"',  # warm salmon
        'deliverable_fill': 'fillcolor="#F7DDBA"',
    },
}


def _view_mode(display: DisplayConfig) -> str:
    return display.view or display.mode or 'overview'


def _label_source(node: Node) -> str:
    return node.path or node.node_id


def _format_label(node: Node, display: DisplayConfig) -> str:
    # Bug 3: technical view always shows the raw node ID.
    if _view_mode(display) == 'technical':
        return node.node_id

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
    if node.node_type in {'script', 'script_placeholder'}:
        lang = node.metadata.get('language', 'stata')
        fill_key = f'{lang}_fill' if f'{lang}_fill' in theme else 'script_fill'
        attrs.append(theme[fill_key])
    if node.role == 'deliverable' and node.node_type == 'artifact':
        attrs.append('style="filled"')
        attrs.append(theme['deliverable_fill'])
    if node.role == 'temporary' and node.node_type == 'artifact':
        if node.metadata.get('erased') == 'true':
            attrs.append('style="dashed"')
            attrs.append('penwidth=2')
        else:
            attrs.append('style="dashed"')
    if node.node_type in {'artifact_placeholder', 'script_placeholder'}:
        if display.placeholder_style == 'filled_dashed':
            attrs.append('style="dashed,filled"')
            attrs.append(theme['deliverable_fill'])
        elif display.placeholder_style == 'bold':
            attrs.append('penwidth=2')
        # default dashed style is already set in _BASE_NODE_STYLE for both placeholder types
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


_XML_MAP = {'&': '&amp;', '<': '&lt;', '>': '&gt;'}


def _xml_escape(text: str) -> str:
    return ''.join(
        _XML_MAP[c] if c in _XML_MAP else (c if ord(c) < 128 else f'&#{ord(c)};')
        for c in text
    )


def _render_cluster_block(
    cluster: Cluster,
    graph: GraphModel,
    visible_nodes: set[str],
    display: DisplayConfig,
    theme: dict[str, str],
    clustered_node_ids: set[str],
    rendered_aliases: dict[str, str],
    indent_level: int,
) -> list[str]:
    """Render one cluster as a subgraph block, recursively rendering child clusters if meta."""
    indent = '  ' * indent_level
    cid = cluster.cluster_id
    raw_label = cluster.label or cid
    xml_label = _xml_escape(raw_label)

    lines: list[str] = []
    lines.append(f'{indent}subgraph "cluster_{cid}" {{')
    lines.append(f'{indent}  label=<<font point-size="11"><b>{xml_label}</b></font>>;')
    lines.append(f'{indent}  style="{theme["cluster_style"]}";')
    lines.append(f'{indent}  color="{theme["cluster_color"]}";')
    lines.append(f'{indent}  penwidth=2.0;')

    if cluster.member_cluster_ids:
        # Meta-cluster: recursively render child clusters inside this subgraph
        for child_id in cluster.member_cluster_ids:
            if child_id in graph.clusters:
                child_cluster = graph.clusters[child_id]
                lines.extend(_render_cluster_block(
                    child_cluster, graph, visible_nodes, display, theme,
                    clustered_node_ids, rendered_aliases,
                    indent_level + 1,
                ))
    else:
        # Leaf cluster: render individual nodes
        member_ids = [
            node_id for node_id in cluster.node_ids
            if node_id in graph.nodes and node_id in visible_nodes
        ]
        clustered_node_ids.update(member_ids)
        for node_id in sorted(member_ids):
            node = graph.nodes[node_id]
            lines.append(f'{indent}  "{node.node_id}" [{_node_attr_string(node, display, theme)}];')
            rendered_aliases[node_id] = node.node_id

    lines.append(f'{indent}}}')
    return lines


def _resolve_theme(name: str) -> dict[str, str]:
    return _THEME_BUNDLES.get(name, _THEME_BUNDLES['modern-light'])


def _should_show_node(node: Node, display: DisplayConfig, terminal_node_ids: set[str] | None = None) -> bool:
    view = _view_mode(display)
    is_script_type = node.node_type in {'script', 'script_placeholder'}
    if view == 'deliverables':
        return is_script_type or node.role in {'deliverable', 'placeholder_artifact', 'reference_input', 'placeholder_script'}
    if view == 'scripts_only':
        return is_script_type
    if view == 'stage_overview':
        return is_script_type and not node.cluster_id
    # Bug 1 fix: hide terminal output nodes when show_terminal_outputs is False.
    # A "terminal output" is an artifact node with no outgoing edges.
    if not display.show_terminal_outputs and terminal_node_ids is not None:
        if node.node_id in terminal_node_ids:
            return False
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
    technical_view = view == 'technical'

    lines = [
        'digraph pipeline {',
        f'  rankdir={rankdir};',
        f'  graph [{theme["graph"]}, newrank=true];',
        f'  node [{theme["node"]}];',
        f'  edge [{theme["edge"]}];',
    ]

    # Bug 1: compute terminal output node IDs (artifacts with no outgoing edges).
    nodes_with_outgoing: set[str] = {edge.source for edge in graph.edges}
    terminal_node_ids: set[str] = {
        node.node_id
        for node in graph.nodes.values()
        if node.node_type in {'artifact', 'artifact_placeholder'}
        and node.node_id not in nodes_with_outgoing
    }

    visible_nodes = {node.node_id for node in graph.sorted_nodes() if _should_show_node(node, display, terminal_node_ids)}
    clustered_node_ids: set[str] = set()
    collapsed_cluster_ids = {
        cluster.cluster_id
        for cluster in graph.sorted_clusters()
        if cluster.metadata.get('collapse') == 'true' or stage_overview
    }
    rendered_aliases: dict[str, str] = {}

    # Build set of clusters that are children of a meta-cluster — they will
    # be rendered nested inside their parent, not at the top level.
    child_cluster_ids: set[str] = set()
    for _c in graph.clusters.values():
        for _cid in _c.member_cluster_ids:
            child_cluster_ids.add(_cid)

    for cluster in graph.sorted_clusters():
        # Child clusters are rendered recursively inside their parent — skip here.
        if cluster.cluster_id in child_cluster_ids:
            continue

        member_ids = [node_id for node_id in cluster.node_ids if node_id in graph.nodes]
        # For meta-clusters, check whether any descendant leaf nodes exist.
        is_meta = bool(cluster.member_cluster_ids)

        if stage_overview:
            # stage_overview only applies to leaf clusters (collapse to summary node).
            if not is_meta:
                member_ids = [node_id for node_id in member_ids if graph.nodes[node_id].node_type in {'script', 'script_placeholder'}]
                if not member_ids:
                    continue
                summary_id = f'cluster::{cluster.cluster_id}'
                lines.append(f'  "{summary_id}" [{_cluster_summary_attr_string(cluster, theme)}];')
                for node_id in member_ids:
                    rendered_aliases[node_id] = summary_id
                clustered_node_ids.update(member_ids)
            continue

        if not is_meta:
            # Leaf cluster: filter to visible nodes.
            member_ids = [node_id for node_id in member_ids if node_id in visible_nodes]
            if not member_ids:
                continue
            if cluster.cluster_id in collapsed_cluster_ids:
                summary_id = f'cluster::{cluster.cluster_id}'
                lines.append(f'  "{summary_id}" [{_cluster_summary_attr_string(cluster, theme)}];')
                for node_id in member_ids:
                    rendered_aliases[node_id] = summary_id
                clustered_node_ids.update(member_ids)
                continue

        # Non-collapsed cluster (leaf or meta): render as subgraph block.
        lines.extend(_render_cluster_block(
            cluster, graph, visible_nodes, display, theme,
            clustered_node_ids, rendered_aliases,
            indent_level=1,
        ))

    unclustered_artifacts: list[str] = []
    for node in graph.sorted_nodes():
        if node.node_id not in visible_nodes or node.node_id in clustered_node_ids:
            continue
        lines.append(f'  "{node.node_id}" [{_node_attr_string(node, display, theme)}];')
        rendered_aliases[node.node_id] = node.node_id
        if node.node_type not in {'script', 'script_placeholder'}:
            unclustered_artifacts.append(node.node_id)

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

    # Bug 3: technical view forces all edge labels on.
    effective_edge_labels = show_edge_labels or technical_view
    if display.edge_label_mode in {'show', 'operation'}:
        effective_edge_labels = True
    elif display.edge_label_mode == 'hidden' and not technical_view:
        effective_edge_labels = False
    # Bug 2: operation mode uses edge.operation instead of edge.visible_label.
    operation_labels_only = display.edge_label_mode == 'operation' and not technical_view

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
        if node.node_type in {'script', 'script_placeholder'}:
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
        # Bug 4: self-loop edges (source == target after alias resolution) are now emitted.
        is_self_loop = source_id == target_id
        # Bug 2: operation mode shows only the operation type, not the full visible_label.
        if effective_edge_labels:
            if operation_labels_only:
                edge_label = edge.operation or ''
            else:
                edge_label = edge.visible_label or ''
        else:
            edge_label = ''
        # For self-loops, use the raw node_id pair as dedupe key (don't suppress duplicates across aliases).
        dedupe_key = (source_id, target_id, edge_label)
        if dedupe_key in emitted_edges:
            continue
        emitted_edges.add(dedupe_key)
        attrs = []
        if edge_label:
            attrs.append(f'label="{_xml_escape(edge_label)}"')
        if is_self_loop:
            attrs.append('comment="self-loop"')
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
