from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath


@dataclass(slots=True)
class Node:
    node_id: str
    label: str
    node_type: str
    path: str | None = None
    role: str | None = None
    cluster_id: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Edge:
    source: str
    target: str
    operation: str
    kind: str
    visible_label: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Diagnostic:
    level: str
    code: str
    message: str
    payload: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class Cluster:
    cluster_id: str
    label: str | None = None
    node_ids: list[str] = field(default_factory=list)
    member_cluster_ids: list[str] = field(default_factory=list)  # for meta-clusters
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class GraphModel:
    project_root: str
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)
    excluded_paths: list[str] = field(default_factory=list)
    clusters: dict[str, Cluster] = field(default_factory=dict)
    metadata: dict[str, str] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        self.nodes.setdefault(node.node_id, node)

    def add_edge(self, edge: Edge) -> None:
        self.edges.append(edge)

    def add_diagnostic(self, diagnostic: Diagnostic) -> None:
        self.diagnostics.append(diagnostic)

    def add_cluster(self, cluster: Cluster) -> None:
        self.clusters.setdefault(cluster.cluster_id, cluster)

    def sorted_nodes(self) -> list[Node]:
        return [self.nodes[key] for key in sorted(self.nodes)]

    def sorted_clusters(self) -> list[Cluster]:
        def _safe_int(value: str | None, fallback: int) -> int:
            try:
                return int(value or '')
            except ValueError:
                return fallback

        def cluster_sort_key(cluster: Cluster) -> tuple[int, str]:
            order = _safe_int(cluster.metadata.get('order'), 1_000_000)
            return order, cluster.cluster_id

        return sorted(self.clusters.values(), key=cluster_sort_key)

    def normalized_path(self, value: str) -> str:
        return str(PurePosixPath(value))
