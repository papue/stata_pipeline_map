from __future__ import annotations

import csv
from pathlib import Path

from data_pipeline_flow.model.entities import Edge, GraphModel, Node

SCRIPT_SUFFIX = '.do'


def _node_type(token: str) -> str:
    return 'script' if token.endswith(SCRIPT_SUFFIX) else 'artifact'


def _label(token: str) -> str:
    return Path(token).name


def load_edge_csv(project_root: Path, edge_csv_path: Path) -> GraphModel:
    graph = GraphModel(project_root=str(project_root))
    with edge_csv_path.open(newline='', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            source = row['source'].strip()
            target = row['target'].strip()
            command = row['command'].strip()
            kind = row['kind'].strip()
            graph.add_node(Node(node_id=source, label=_label(source), node_type=_node_type(source), path=source, role=kind))
            graph.add_node(Node(node_id=target, label=_label(target), node_type=_node_type(target), path=target, role=kind))
            visible_label = None if command in {'merge', 'append', 'cross'} else command
            graph.add_edge(Edge(source=source, target=target, operation=command, kind=kind, visible_label=visible_label))
    return graph
