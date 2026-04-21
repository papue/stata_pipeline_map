from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import re

from data_pipeline_flow.config.schema import VersionFamiliesConfig
from data_pipeline_flow.model.entities import Diagnostic, Edge, GraphModel

_VERSION_TOKEN_RE = re.compile(r'(?i)(?:_v\d+|_(?:qc|pp|final|draft))(?=\.[^.]+$)')
_NUMERIC_VERSION_RE = re.compile(r'(?i)_v(\d+)(?=\.[^.]+$)')
_SUFFIX_TOKEN_RE = re.compile(r'(?i)_([a-z][a-z0-9]*)(?=\.[^.]+$)')


def _family_key(path: str) -> str | None:
    file_path = Path(path)
    normalized_name = _VERSION_TOKEN_RE.sub('', file_path.name)
    if normalized_name == file_path.name:
        return None
    return (str(Path(file_path.parent) / normalized_name)).replace('\\', '/')


def _choose_latest_modified(members: list[str], project_root: Path) -> str | None:
    existing: list[tuple[float, str]] = []
    for member in members:
        candidate = project_root / member
        if candidate.exists():
            existing.append((candidate.stat().st_mtime, member))
    if not existing:
        return None
    existing.sort(key=lambda item: (item[0], item[1]), reverse=True)
    return existing[0][1]


def _choose_highest_numeric(members: list[str], project_root: Path, tiebreaker: str) -> str | None:
    numeric: list[tuple[int, str]] = []
    for member in members:
        match = _NUMERIC_VERSION_RE.search(Path(member).name)
        if match:
            numeric.append((int(match.group(1)), member))
    if not numeric:
        return None
    numeric.sort(reverse=True)
    highest = numeric[0][0]
    top_members = sorted({member for value, member in numeric if value == highest})
    if len(top_members) == 1:
        return top_members[0]
    if tiebreaker == 'latest_modified':
        return _choose_latest_modified(top_members, project_root)
    return top_members[-1]


def _choose_priority_suffix(members: list[str], priority_suffixes: list[str], project_root: Path, tiebreaker: str) -> str | None:
    priority_order = {suffix.lower(): index for index, suffix in enumerate(priority_suffixes)}
    ranked: list[tuple[int, str]] = []
    for member in members:
        match = _SUFFIX_TOKEN_RE.search(Path(member).name)
        if not match:
            continue
        suffix = match.group(1).lower()
        if suffix in priority_order:
            ranked.append((priority_order[suffix], member))
    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1]))
    best_rank = ranked[0][0]
    top_members = sorted({member for rank, member in ranked if rank == best_rank})
    if len(top_members) == 1:
        return top_members[0]
    if tiebreaker == 'latest_modified':
        return _choose_latest_modified(top_members, project_root)
    return top_members[-1]


def _dedupe_edges(edges: list[Edge]) -> list[Edge]:
    deduped: list[Edge] = []
    seen: set[tuple[str, str, str, str, str | None]] = set()
    for edge in edges:
        key = (edge.source, edge.target, edge.operation, edge.kind, edge.visible_label)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(edge)
    return deduped


def apply_version_family_resolution(graph: GraphModel, project_root: Path, config: VersionFamiliesConfig) -> GraphModel:
    if config.mode in {'off', 'detect_only'}:
        return graph

    families: dict[str, list[str]] = defaultdict(list)
    for node in graph.nodes.values():
        if node.node_type not in {'artifact', 'artifact_placeholder'} or node.path is None:
            continue
        family_key = _family_key(node.path)
        if family_key:
            families[family_key].append(node.node_id)

    replacements: dict[str, str] = {}
    removed_nodes: set[str] = set()

    for family_key, members in sorted(families.items()):
        unique_members = sorted(set(members))
        if len(unique_members) < 2:
            continue

        chosen: str | None = None
        if config.mode == 'prefer_latest_modified':
            chosen = _choose_latest_modified(unique_members, project_root)
        elif config.mode == 'prefer_highest_numeric':
            chosen = _choose_highest_numeric(unique_members, project_root, config.tiebreaker)
        elif config.mode == 'prefer_priority_suffix':
            chosen = _choose_priority_suffix(unique_members, config.priority_suffixes, project_root, config.tiebreaker)

        if chosen is None:
            graph.add_diagnostic(
                Diagnostic(
                    level='warning',
                    code='version_family_ambiguous',
                    message=f'Could not resolve version family under mode {config.mode}: {family_key}',
                    payload={'family': family_key, 'members': ' | '.join(unique_members), 'mode': config.mode},
                )
            )
            continue

        canonical = graph.nodes.get(chosen)
        if canonical is None:
            continue
        canonical.metadata['version_family'] = family_key
        canonical.metadata['version_family_mode'] = config.mode
        canonical.metadata['version_family_members'] = ' | '.join(unique_members)

        for member in unique_members:
            replacements[member] = chosen
            if member != chosen:
                removed_nodes.add(member)

        graph.add_diagnostic(
            Diagnostic(
                level='info',
                code='version_family_resolved',
                message=f'Resolved version family to canonical member: {family_key}',
                payload={'family': family_key, 'chosen': chosen, 'members': ' | '.join(unique_members), 'mode': config.mode},
            )
        )

    if not replacements:
        return graph

    for edge in graph.edges:
        edge.source = replacements.get(edge.source, edge.source)
        edge.target = replacements.get(edge.target, edge.target)
    graph.edges = _dedupe_edges(graph.edges)

    for cluster in graph.clusters.values():
        cluster.node_ids = sorted({replacements.get(node_id, node_id) for node_id in cluster.node_ids if replacements.get(node_id, node_id) in graph.nodes})

    for node_id in removed_nodes:
        graph.nodes.pop(node_id, None)

    return graph
