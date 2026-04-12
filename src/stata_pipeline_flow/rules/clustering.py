from __future__ import annotations

from collections import defaultdict
from pathlib import PurePosixPath

from stata_pipeline_flow.model.entities import Cluster, GraphModel

SCRIPT_NODE_TYPE = 'script'


def infer_clusters(graph: GraphModel) -> GraphModel:
    graph.clusters.clear()
    for node in graph.nodes.values():
        node.cluster_id = None

    scripts_by_folder = _scripts_by_folder(graph)
    if not scripts_by_folder:
        return graph

    dependencies = _build_script_dependencies(graph)
    folder_components = _folder_components(scripts_by_folder, dependencies)

    cluster_index = 1
    for folders in folder_components:
        member_scripts = sorted(
            script_id
            for folder in folders
            for script_id in scripts_by_folder.get(folder, [])
        )
        if not member_scripts:
            continue

        cluster_id = f'cluster_{cluster_index:03d}'
        label = _cluster_label(folders)
        cluster = Cluster(
            cluster_id=cluster_id,
            label=label,
            node_ids=list(member_scripts),
            metadata={
                'kind': 'auto',
                'folder_count': str(len(folders)),
                'script_count': str(len(member_scripts)),
                'order': str(1000 + cluster_index),
            },
        )
        graph.add_cluster(cluster)
        for node_id in member_scripts:
            graph.nodes[node_id].cluster_id = cluster_id
        cluster_index += 1

    assign_artifact_clusters(graph)
    return graph


def assign_artifact_clusters(graph: GraphModel, protected_node_ids: set[str] | None = None) -> GraphModel:
    protected_node_ids = protected_node_ids or set()

    for node in graph.sorted_nodes():
        if node.node_type == SCRIPT_NODE_TYPE or node.node_id in protected_node_ids:
            continue
        if node.cluster_id is None:
            continue
        cluster = graph.clusters.get(node.cluster_id)
        if cluster is not None and node.node_id in cluster.node_ids:
            cluster.node_ids.remove(node.node_id)
        node.cluster_id = None

    for node in graph.sorted_nodes():
        if node.node_type == SCRIPT_NODE_TYPE or node.node_id in protected_node_ids:
            continue
        neighbor_clusters = {
            graph.nodes[neighbor_id].cluster_id
            for neighbor_id in _script_neighbors(graph, node.node_id)
            if graph.nodes[neighbor_id].cluster_id is not None
        }
        if len(neighbor_clusters) != 1:
            continue
        cluster_id = next(iter(neighbor_clusters))
        node.cluster_id = cluster_id
        cluster = graph.clusters.get(cluster_id)
        if cluster is not None and node.node_id not in cluster.node_ids:
            cluster.node_ids.append(node.node_id)
            cluster.node_ids.sort()

    return graph


def _scripts_by_folder(graph: GraphModel) -> dict[str, list[str]]:
    scripts_by_folder: dict[str, list[str]] = defaultdict(list)
    for node in graph.sorted_nodes():
        if node.node_type != SCRIPT_NODE_TYPE:
            continue
        folder = _parent_dir(node.node_id)
        scripts_by_folder[folder].append(node.node_id)
    return {folder: sorted(node_ids) for folder, node_ids in scripts_by_folder.items()}


def _build_script_dependencies(graph: GraphModel) -> set[tuple[str, str]]:
    dependencies: set[tuple[str, str]] = set()

    for edge in graph.edges:
        source = graph.nodes.get(edge.source)
        target = graph.nodes.get(edge.target)
        if source and target and source.node_type == SCRIPT_NODE_TYPE and target.node_type == SCRIPT_NODE_TYPE:
            dependencies.add((edge.source, edge.target))

    artifact_writers: dict[str, set[str]] = defaultdict(set)
    artifact_readers: dict[str, set[str]] = defaultdict(set)
    for edge in graph.edges:
        source = graph.nodes.get(edge.source)
        target = graph.nodes.get(edge.target)
        if not source or not target:
            continue
        if source.node_type == SCRIPT_NODE_TYPE and target.node_type != SCRIPT_NODE_TYPE:
            artifact_writers[target.node_id].add(source.node_id)
        elif source.node_type != SCRIPT_NODE_TYPE and target.node_type == SCRIPT_NODE_TYPE:
            artifact_readers[source.node_id].add(target.node_id)

    for artifact_id, writers in artifact_writers.items():
        for writer in writers:
            for reader in artifact_readers.get(artifact_id, set()):
                if writer != reader:
                    dependencies.add((writer, reader))

    return dependencies


def _folder_components(
    scripts_by_folder: dict[str, list[str]],
    dependencies: set[tuple[str, str]],
) -> list[list[str]]:
    folders = sorted(scripts_by_folder)
    folder_incoming: dict[str, set[str]] = {folder: set() for folder in folders}
    folder_outgoing: dict[str, set[str]] = {folder: set() for folder in folders}

    for source, target in dependencies:
        source_folder = _parent_dir(source)
        target_folder = _parent_dir(target)
        if source_folder == target_folder:
            continue
        folder_outgoing.setdefault(source_folder, set()).add(target_folder)
        folder_incoming.setdefault(target_folder, set()).add(source_folder)

    adjacency: dict[str, set[str]] = {folder: set() for folder in folders}
    for source_folder in folders:
        for target_folder in sorted(folder_outgoing.get(source_folder, set())):
            if _should_merge_folders(source_folder, target_folder, folder_incoming, folder_outgoing):
                adjacency[source_folder].add(target_folder)
                adjacency[target_folder].add(source_folder)

    components: list[list[str]] = []
    seen: set[str] = set()
    for folder in folders:
        if folder in seen:
            continue
        stack = [folder]
        members: list[str] = []
        seen.add(folder)
        while stack:
            current = stack.pop()
            members.append(current)
            for neighbor in sorted(adjacency[current], reverse=True):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        components.append(sorted(members))

    components.sort(key=lambda member_folders: member_folders[0])
    return components


def _should_merge_folders(
    source_folder: str,
    target_folder: str,
    folder_incoming: dict[str, set[str]],
    folder_outgoing: dict[str, set[str]],
) -> bool:
    if _directory_distance(source_folder, target_folder) > 2:
        return False
    if len(folder_outgoing.get(source_folder, set())) != 1:
        return False
    if len(folder_incoming.get(target_folder, set())) != 1:
        return False
    return True


def _script_neighbors(graph: GraphModel, node_id: str) -> set[str]:
    neighbors: set[str] = set()
    for edge in graph.edges:
        if edge.source == node_id and graph.nodes.get(edge.target) and graph.nodes[edge.target].node_type == SCRIPT_NODE_TYPE:
            neighbors.add(edge.target)
        elif edge.target == node_id and graph.nodes.get(edge.source) and graph.nodes[edge.source].node_type == SCRIPT_NODE_TYPE:
            neighbors.add(edge.source)
    return neighbors


def _cluster_label(folders: list[str]) -> str:
    if not folders:
        return 'Pipeline stage'
    if len(folders) == 1:
        return folders[0] or '.'
    common_prefix = _common_path_prefix(folders)
    if common_prefix:
        return f'{common_prefix} / chain'
    return 'Pipeline stage'


def _common_path_prefix(paths: list[str]) -> str:
    split_paths = [PurePosixPath(path).parts for path in paths if path]
    if not split_paths:
        return ''
    prefix_parts: list[str] = []
    for parts in zip(*split_paths):
        if len(set(parts)) != 1:
            break
        prefix_parts.append(parts[0])
    return str(PurePosixPath(*prefix_parts)) if prefix_parts else ''


def _parent_dir(path: str) -> str:
    parent = PurePosixPath(path).parent
    return '' if str(parent) == '.' else str(parent)


def _directory_distance(left: str, right: str) -> int:
    left_parts = PurePosixPath(left).parts
    right_parts = PurePosixPath(right).parts
    shared = 0
    for left_part, right_part in zip(left_parts, right_parts):
        if left_part != right_part:
            break
        shared += 1
    return (len(left_parts) - shared) + (len(right_parts) - shared)
