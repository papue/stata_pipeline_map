from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
import json

try:
    import yaml  # type: ignore
except Exception:  # pragma: no cover
    yaml = None


@dataclass(slots=True)
class DisplayConfig:
    show_edge_labels: bool = False
    mode: str = 'overview'
    theme: str = 'modern-light'
    show_terminal_outputs: bool = True
    show_temporary_outputs: bool = False
    placeholder_style: str = 'dashed'
    label_path_depth: int = 0
    show_extensions: bool = True
    node_label_style: str = 'basename'
    view: str = 'overview'
    edge_label_mode: str = 'auto'


@dataclass(slots=True)
class ExclusionConfig:
    prefixes: list[str] = field(default_factory=list)
    globs: list[str] = field(default_factory=lambda: ['*.tmp', '*.bak'])
    exact_names: list[str] = field(default_factory=list)
    exact_paths: list[str] = field(default_factory=list)
    folder_names: list[str] = field(default_factory=list)
    paths: list[str] = field(default_factory=list)
    file_names: list[str] = field(default_factory=list)
    presets: list[str] = field(default_factory=lambda: ['generated_outputs', 'archival_folders', 'python_runtime'])


@dataclass(slots=True)
class NormalizationConfig:
    path_prefix_aliases: dict[str, str] = field(default_factory=dict)
    project_root_markers: list[str] = field(default_factory=list)
    strip_leading_dot: bool = True


@dataclass(slots=True)
class DynamicPathsConfig:
    mode: str = 'resolve_simple'
    placeholder_token: str = '{dynamic}'


@dataclass(slots=True)
class VersionFamiliesConfig:
    mode: str = 'detect_only'
    priority_suffixes: list[str] = field(default_factory=lambda: ['qc', 'pp', 'final', 'draft'])
    tiebreaker: str = 'latest_modified'


@dataclass(slots=True)
class ParserConfig:
    edge_csv_path: str = 'viewer_output/parser_edges.csv'
    prefer_existing_edge_csv: bool = False
    write_edge_csv: bool = True
    suppress_internal_only_writes: bool = True
    dynamic_paths: DynamicPathsConfig = field(default_factory=DynamicPathsConfig)
    version_families: VersionFamiliesConfig = field(default_factory=VersionFamiliesConfig)


@dataclass(slots=True)
class ClassificationConfig:
    deliverable_extensions: list[str] = field(default_factory=lambda: ['.csv', '.xlsx', '.pdf', '.png', '.svg', '.docx', '.tex', '.ster'])
    temporary_name_patterns: list[str] = field(default_factory=lambda: ['_tmp', '_temp', '_scratch', 'temp_', 'tmp_'])


@dataclass(slots=True)
class ClusteringConfig:
    enabled: bool = True
    strategy: str = 'auto'


@dataclass(slots=True)
class ClusterLaneConfig:
    lane: str
    cluster_ids: list[str] = field(default_factory=list)


@dataclass(slots=True)
class LayoutConfig:
    rankdir: str = 'LR'
    cluster_lanes: list[ClusterLaneConfig] = field(default_factory=list)
    unclustered_artifacts_position: str = 'auto'


@dataclass(slots=True)
class ManualClusterConfig:
    cluster_id: str
    label: str | None = None
    members: list[str] = field(default_factory=list)
    lane: str | None = None
    order: int | None = None
    collapse: bool = False


@dataclass(slots=True)
class AppConfig:
    project_root: str = '.'
    display: DisplayConfig = field(default_factory=DisplayConfig)
    exclusions: ExclusionConfig = field(default_factory=ExclusionConfig)
    normalization: NormalizationConfig = field(default_factory=NormalizationConfig)
    parser: ParserConfig = field(default_factory=ParserConfig)
    classification: ClassificationConfig = field(default_factory=ClassificationConfig)
    clustering: ClusteringConfig = field(default_factory=ClusteringConfig)
    layout: LayoutConfig = field(default_factory=LayoutConfig)
    clusters: list[ManualClusterConfig] = field(default_factory=list)


def _merge_dataclass_config(cls: type, raw: dict[str, Any]) -> Any:
    allowed = {name for name in cls.__dataclass_fields__}
    filtered = {k: v for k, v in raw.items() if k in allowed}
    return cls(**filtered)


def _load_cluster_lanes(raw_lanes: Any) -> list[ClusterLaneConfig]:
    if raw_lanes in (None, ''):
        return []
    if not isinstance(raw_lanes, list):
        raise ValueError('Config field "layout.cluster_lanes" must be a list of lane definitions.')

    lanes: list[ClusterLaneConfig] = []
    for index, raw_lane in enumerate(raw_lanes, start=1):
        if not isinstance(raw_lane, dict):
            raise ValueError(f'Lane entry #{index} must be a mapping.')
        lane_value = str(raw_lane.get('lane') or raw_lane.get('id') or '').strip()
        if not lane_value:
            raise ValueError(f'Lane entry #{index} is missing "lane" or "id".')
        raw_cluster_ids = raw_lane.get('cluster_ids') or raw_lane.get('clusters') or []
        if not isinstance(raw_cluster_ids, list):
            raise ValueError(f'Lane "{lane_value}" cluster ids must be a list.')
        cluster_ids = [str(cluster_id).strip() for cluster_id in raw_cluster_ids if str(cluster_id).strip()]
        lanes.append(ClusterLaneConfig(lane=lane_value, cluster_ids=cluster_ids))
    return lanes


def _load_manual_clusters(raw_clusters: Any) -> list[ManualClusterConfig]:
    if raw_clusters in (None, ''):
        return []
    if not isinstance(raw_clusters, list):
        raise ValueError('Config field "clusters" must be a list of cluster definitions.')

    clusters: list[ManualClusterConfig] = []
    for index, raw_cluster in enumerate(raw_clusters, start=1):
        if not isinstance(raw_cluster, dict):
            raise ValueError(f'Cluster entry #{index} must be a mapping.')
        cluster_id = str(raw_cluster.get('cluster_id') or raw_cluster.get('id') or '').strip()
        if not cluster_id:
            raise ValueError(f'Cluster entry #{index} is missing "id" or "cluster_id".')

        label = raw_cluster.get('label')
        label_value = None if label in (None, '') else str(label)
        members = raw_cluster.get('members', [])
        if members is None:
            members = []
        if not isinstance(members, list):
            raise ValueError(f'Cluster "{cluster_id}" members must be a list of paths.')

        cleaned_members: list[str] = []
        for member in members:
            cleaned = str(member).strip()
            if cleaned:
                cleaned_members.append(cleaned)

        lane_raw = raw_cluster.get('lane')
        lane = None if lane_raw in (None, '') else str(lane_raw).strip()
        order_raw = raw_cluster.get('order')
        order = None if order_raw in (None, '') else int(order_raw)
        collapse = bool(raw_cluster.get('collapse', False))

        clusters.append(
            ManualClusterConfig(
                cluster_id=cluster_id,
                label=label_value,
                members=cleaned_members,
                lane=lane,
                order=order,
                collapse=collapse,
            )
        )
    return clusters




_ALLOWED_DISPLAY_THEMES = {'modern-light', 'modern-dark', 'warm-neutral'}
_ALLOWED_DISPLAY_VIEWS = {'overview', 'deliverables', 'technical', 'scripts_only', 'stage_overview'}
_ALLOWED_NODE_LABEL_STYLES = {'basename', 'stem', 'full_path'}
_ALLOWED_PLACEHOLDER_STYLES = {'dashed', 'filled_dashed', 'bold'}
_ALLOWED_EDGE_LABEL_MODES = {'auto', 'hidden', 'show', 'operation'}
_ALLOWED_DYNAMIC_PATH_MODES = {'literal_only', 'resolve_simple', 'resolve_loops', 'resolve_loops_with_placeholders'}
_ALLOWED_VERSION_FAMILY_MODES = {'off', 'detect_only', 'prefer_latest_modified', 'prefer_highest_numeric', 'prefer_priority_suffix'}


def _coerce_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def sanitize_config(config: AppConfig) -> AppConfig:
    if config.display.theme not in _ALLOWED_DISPLAY_THEMES:
        config.display.theme = 'modern-light'
    if config.display.view not in _ALLOWED_DISPLAY_VIEWS:
        config.display.view = 'overview'
    if config.display.node_label_style not in _ALLOWED_NODE_LABEL_STYLES:
        config.display.node_label_style = 'basename'
    if config.display.placeholder_style not in _ALLOWED_PLACEHOLDER_STYLES:
        config.display.placeholder_style = 'dashed'
    if config.display.edge_label_mode not in _ALLOWED_EDGE_LABEL_MODES:
        config.display.edge_label_mode = 'auto'
    try:
        config.display.label_path_depth = max(0, int(config.display.label_path_depth))
    except (TypeError, ValueError):
        config.display.label_path_depth = 0
    config.display.show_extensions = _coerce_bool(config.display.show_extensions, True)
    config.display.show_terminal_outputs = _coerce_bool(config.display.show_terminal_outputs, True)
    config.display.show_temporary_outputs = _coerce_bool(config.display.show_temporary_outputs, False)
    config.display.show_edge_labels = _coerce_bool(config.display.show_edge_labels, False)

    if config.parser.dynamic_paths.mode not in _ALLOWED_DYNAMIC_PATH_MODES:
        config.parser.dynamic_paths.mode = 'resolve_simple'
    if config.parser.version_families.mode not in _ALLOWED_VERSION_FAMILY_MODES:
        config.parser.version_families.mode = 'detect_only'
    if not isinstance(config.parser.dynamic_paths.placeholder_token, str) or not config.parser.dynamic_paths.placeholder_token:
        config.parser.dynamic_paths.placeholder_token = '{dynamic}'

    return config

def load_config(path: Path) -> AppConfig:
    suffix = path.suffix.lower()
    text = path.read_text(encoding='utf-8')
    if suffix in {'.yaml', '.yml'}:
        if yaml is None:
            raise RuntimeError('YAML config requested but PyYAML is not installed.')
        raw = yaml.safe_load(text) or {}
    else:
        raw = json.loads(text)

    display = _merge_dataclass_config(DisplayConfig, raw.get('display', {}))
    exclusions = _merge_dataclass_config(ExclusionConfig, raw.get('exclusions', {}))
    normalization = _merge_dataclass_config(NormalizationConfig, raw.get('normalization', {}))

    raw_parser = dict(raw.get('parser', {}))
    dynamic_paths = _merge_dataclass_config(DynamicPathsConfig, raw_parser.get('dynamic_paths', {}))
    version_families = _merge_dataclass_config(VersionFamiliesConfig, raw_parser.get('version_families', {}))
    parser = _merge_dataclass_config(ParserConfig, raw_parser)
    parser.dynamic_paths = dynamic_paths
    parser.version_families = version_families

    classification = _merge_dataclass_config(ClassificationConfig, raw.get('classification', {}))
    clustering = _merge_dataclass_config(ClusteringConfig, raw.get('clustering', {}))

    raw_layout = dict(raw.get('layout', {}))
    layout = _merge_dataclass_config(LayoutConfig, raw_layout)
    layout.cluster_lanes = _load_cluster_lanes(raw_layout.get('cluster_lanes', []))

    manual_clusters = _load_manual_clusters(raw.get('clusters', []))
    return sanitize_config(AppConfig(
        project_root=raw.get('project_root', '.'),
        display=display,
        exclusions=exclusions,
        normalization=normalization,
        parser=parser,
        classification=classification,
        clustering=clustering,
        layout=layout,
        clusters=manual_clusters,
    ))
