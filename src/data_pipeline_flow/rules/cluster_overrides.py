from __future__ import annotations

import difflib
from collections import defaultdict

from data_pipeline_flow.config.schema import ManualClusterConfig
from data_pipeline_flow.model.entities import Cluster, Diagnostic, GraphModel
from data_pipeline_flow.rules.clustering import assign_artifact_clusters


def apply_manual_clusters(graph: GraphModel, clusters: list[ManualClusterConfig]) -> GraphModel:
    if not clusters:
        return graph

    _validate_manual_clusters(graph, clusters)

    configured_nodes: set[str] = set()
    applied_count = 0

    for order, cluster_config in enumerate(clusters, start=1):
        cluster_id = cluster_config.cluster_id.strip()
        if not cluster_id:
            graph.add_diagnostic(
                Diagnostic(
                    level='warning',
                    code='invalid_manual_cluster',
                    message='Skipped a manual cluster definition with an empty id.',
                )
            )
            continue

        cluster = graph.clusters.get(cluster_id)
        if cluster is None:
            cluster = Cluster(cluster_id=cluster_id)
            graph.add_cluster(cluster)

        if cluster_config.label is not None:
            cluster.label = cluster_config.label
        elif cluster.label is None:
            cluster.label = cluster_id

        cluster.metadata['kind'] = 'manual'
        cluster.metadata['configured_member_count'] = str(len(cluster_config.members))
        if cluster_config.order is not None:
            cluster.metadata['order'] = str(cluster_config.order)
        elif 'order' not in cluster.metadata:
            cluster.metadata['order'] = str(order)
        if cluster_config.collapse:
            cluster.metadata['collapse'] = 'true'
        elif 'collapse' not in cluster.metadata:
            cluster.metadata['collapse'] = 'false'

        for member in cluster_config.members:
            node = graph.nodes.get(member)
            if node is None:
                close = difflib.get_close_matches(member, list(graph.nodes.keys()), n=1, cutoff=0.6)
                hint = f' (did you mean: {close[0]}?)' if close else ''
                graph.add_diagnostic(
                    Diagnostic(
                        level='warning',
                        code='cluster_member_not_found',
                        message=f'Manual cluster member was not found in the graph: {member}{hint}',
                        payload={'cluster_id': cluster_id, 'member': member},
                    )
                )
                continue
            _assign_node_to_cluster(graph, node.node_id, cluster_id)
            configured_nodes.add(node.node_id)
            applied_count += 1

    _prune_empty_clusters(graph)
    assign_artifact_clusters(graph, protected_node_ids=configured_nodes)
    _prune_empty_clusters(graph)

    # Second pass: apply meta-clusters (clusters whose members are other cluster IDs)
    for cluster_config in clusters:
        if not cluster_config.member_cluster_ids:
            continue
        cluster_id = cluster_config.cluster_id.strip()
        if not cluster_id:
            continue
        cluster = graph.clusters.get(cluster_id)
        if cluster is None:
            cluster = Cluster(cluster_id=cluster_id)
            graph.add_cluster(cluster)
        if cluster_config.label is not None:
            cluster.label = cluster_config.label
        elif cluster.label is None:
            cluster.label = cluster_id
        cluster.metadata['kind'] = 'manual'
        cluster.metadata['meta_cluster'] = 'true'
        if cluster_config.order is not None:
            cluster.metadata['order'] = str(cluster_config.order)
        elif 'order' not in cluster.metadata:
            cluster.metadata['order'] = str(len(graph.clusters))
        cluster.member_cluster_ids = list(cluster_config.member_cluster_ids)

    graph.add_diagnostic(
        Diagnostic(
            level='info',
            code='manual_clusters_applied',
            message=f'Applied {len(clusters)} manual cluster definitions.',
            payload={
                'clusters': str(len(clusters)),
                'assigned_nodes': str(applied_count),
            },
        )
    )
    return graph


def _validate_manual_clusters(graph: GraphModel, clusters: list[ManualClusterConfig]) -> None:
    cluster_id_entries: dict[str, list[int]] = defaultdict(list)
    member_to_cluster_ids: dict[str, list[str]] = defaultdict(list)

    # Collect all defined cluster IDs for cross-reference validation
    all_defined_cluster_ids: set[str] = {c.cluster_id.strip() for c in clusters if c.cluster_id.strip()}

    for index, cluster_config in enumerate(clusters, start=1):
        cluster_id = cluster_config.cluster_id.strip()
        if cluster_id:
            cluster_id_entries[cluster_id].append(index)

        has_members = bool(cluster_config.members)
        has_member_cluster_ids = bool(cluster_config.member_cluster_ids)

        # Mutual exclusivity: members and member_cluster_ids cannot both be set
        if has_members and has_member_cluster_ids:
            graph.add_diagnostic(
                Diagnostic(
                    level='warning',
                    code='invalid_meta_cluster',
                    message=(
                        f'Manual cluster "{cluster_id or f"entry #{index}"}" has both "members" and '
                        '"member_cluster_ids" set. These are mutually exclusive; "member_cluster_ids" will be used.'
                    ),
                    payload={
                        'cluster_id': cluster_id,
                        'entry_index': str(index),
                    },
                )
            )

        if not has_members and not has_member_cluster_ids:
            graph.add_diagnostic(
                Diagnostic(
                    level='warning',
                    code='empty_manual_cluster',
                    message=f'Manual cluster "{cluster_id or f"entry #{index}"}" has no members configured.',
                    payload={
                        'cluster_id': cluster_id,
                        'entry_index': str(index),
                    },
                )
            )

        for member in cluster_config.members:
            member_to_cluster_ids[member].append(cluster_id)

        # Validate meta-cluster references
        for ref_id in cluster_config.member_cluster_ids:
            if ref_id == cluster_id:
                graph.add_diagnostic(
                    Diagnostic(
                        level='warning',
                        code='meta_cluster_self_reference',
                        message=f'Meta-cluster "{cluster_id}" references itself in member_cluster_ids.',
                        payload={'cluster_id': cluster_id, 'ref_id': ref_id},
                    )
                )
            elif ref_id not in all_defined_cluster_ids:
                graph.add_diagnostic(
                    Diagnostic(
                        level='warning',
                        code='meta_cluster_unknown_ref',
                        message=(
                            f'Meta-cluster "{cluster_id}" references cluster "{ref_id}" '
                            'which is not defined in the manual cluster config.'
                        ),
                        payload={'cluster_id': cluster_id, 'ref_id': ref_id},
                    )
                )

    for cluster_id, entry_indexes in sorted(cluster_id_entries.items()):
        if len(entry_indexes) < 2:
            continue
        graph.add_diagnostic(
            Diagnostic(
                level='warning',
                code='duplicate_manual_cluster_id',
                message=(
                    f'Manual cluster id "{cluster_id}" is defined multiple times '
                    f'(entries {", ".join(str(index) for index in entry_indexes)}). '
                    'Definitions are applied in order.'
                ),
                payload={
                    'cluster_id': cluster_id,
                    'entries': ','.join(str(index) for index in entry_indexes),
                    'count': str(len(entry_indexes)),
                },
            )
        )

    for member, cluster_ids in sorted(member_to_cluster_ids.items()):
        unique_cluster_ids = sorted({cluster_id for cluster_id in cluster_ids if cluster_id})
        if len(unique_cluster_ids) < 2:
            continue
        graph.add_diagnostic(
            Diagnostic(
                level='warning',
                code='duplicate_manual_cluster_member',
                message=(
                    f'Manual cluster member "{member}" appears in multiple manual clusters: '
                    f'{", ".join(unique_cluster_ids)}. Later assignments override earlier ones.'
                ),
                payload={
                    'member': member,
                    'cluster_ids': '|'.join(unique_cluster_ids),
                    'count': str(len(unique_cluster_ids)),
                },
            )
        )

    # Detect cycles in meta-cluster member_cluster_ids references
    adjacency: dict[str, list[str]] = {
        c.cluster_id.strip(): list(c.member_cluster_ids)
        for c in clusters
        if c.cluster_id.strip() and c.member_cluster_ids
    }
    reported_cycles: set[frozenset[str]] = set()
    for start in adjacency:
        path: list[str] = []
        visited_stack: set[str] = set()

        def _dfs(node: str) -> None:
            if node in visited_stack:
                # Found a cycle; extract the cycle portion
                cycle_start = path.index(node)
                cycle = path[cycle_start:]
                cycle_key = frozenset(cycle)
                if cycle_key not in reported_cycles:
                    reported_cycles.add(cycle_key)
                    cycle_path = ' -> '.join(cycle + [node])
                    graph.add_diagnostic(
                        Diagnostic(
                            level='warning',
                            code='meta_cluster_cycle',
                            message=(
                                f'Cycle detected in meta-cluster member_cluster_ids: {cycle_path}. '
                                'Affected clusters may be empty.'
                            ),
                            payload={
                                'cycle': cycle_path,
                                'cluster_ids': '|'.join(sorted(cycle)),
                            },
                        )
                    )
                return
            if node not in adjacency:
                return
            visited_stack.add(node)
            path.append(node)
            for neighbour in adjacency[node]:
                _dfs(neighbour)
            path.pop()
            visited_stack.discard(node)

        _dfs(start)


def _assign_node_to_cluster(graph: GraphModel, node_id: str, cluster_id: str) -> None:
    node = graph.nodes[node_id]
    if node.cluster_id == cluster_id:
        cluster = graph.clusters.get(cluster_id)
        if cluster is not None and node_id not in cluster.node_ids:
            cluster.node_ids.append(node_id)
            cluster.node_ids.sort()
        return

    if node.cluster_id is not None:
        previous_cluster = graph.clusters.get(node.cluster_id)
        if previous_cluster is not None and node_id in previous_cluster.node_ids:
            previous_cluster.node_ids.remove(node_id)

    node.cluster_id = cluster_id
    cluster = graph.clusters.get(cluster_id)
    if cluster is None:
        cluster = Cluster(cluster_id=cluster_id)
        graph.add_cluster(cluster)
    if node_id not in cluster.node_ids:
        cluster.node_ids.append(node_id)
        cluster.node_ids.sort()


def _prune_empty_clusters(graph: GraphModel) -> None:
    empty_cluster_ids = [
        cluster_id
        for cluster_id, cluster in graph.clusters.items()
        if not cluster.node_ids and not cluster.member_cluster_ids
    ]
    for cluster_id in empty_cluster_ids:
        graph.clusters.pop(cluster_id, None)
