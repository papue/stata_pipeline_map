from __future__ import annotations

from stata_pipeline_flow.config.schema import LayoutConfig
from stata_pipeline_flow.model.entities import Diagnostic, GraphModel

_ALLOWED_RANKDIR = {'LR', 'TB'}
_ALLOWED_UNCLUSTERED_ARTIFACTS_POSITION = {'auto', 'left', 'right', 'separate_lane'}


def apply_layout_config(graph: GraphModel, layout: LayoutConfig) -> GraphModel:
    rankdir = (layout.rankdir or 'LR').upper()
    if rankdir not in _ALLOWED_RANKDIR:
        graph.add_diagnostic(
            Diagnostic(
                level='warning',
                code='invalid_layout_rankdir',
                message=f'Invalid layout.rankdir "{layout.rankdir}". Falling back to LR.',
                payload={'value': str(layout.rankdir), 'fallback': 'LR'},
            )
        )
        rankdir = 'LR'
    graph.metadata['rankdir'] = rankdir

    artifact_position = str(layout.unclustered_artifacts_position or 'auto')
    if artifact_position not in _ALLOWED_UNCLUSTERED_ARTIFACTS_POSITION:
        graph.add_diagnostic(
            Diagnostic(
                level='warning',
                code='invalid_unclustered_artifacts_position',
                message=(
                    f'Invalid layout.unclustered_artifacts_position "{layout.unclustered_artifacts_position}". '
                    'Falling back to auto.'
                ),
                payload={'value': artifact_position, 'fallback': 'auto'},
            )
        )
        artifact_position = 'auto'
    graph.metadata['unclustered_artifacts_position'] = artifact_position

    lane_sort_index = 0
    for lane_index, lane_config in enumerate(layout.cluster_lanes, start=1):
        lane_value = lane_config.lane
        if not lane_value:
            continue
        for cluster_position, cluster_id in enumerate(lane_config.cluster_ids, start=1):
            cluster = graph.clusters.get(cluster_id)
            if cluster is None:
                graph.add_diagnostic(
                    Diagnostic(
                        level='warning',
                        code='layout_lane_missing_cluster',
                        message=f'layout.cluster_lanes references missing cluster "{cluster_id}".',
                        payload={'lane': lane_value, 'cluster_id': cluster_id},
                    )
                )
                continue
            cluster.metadata['lane'] = lane_value
            cluster.metadata['lane_sort'] = str(lane_index)
            if 'order' not in cluster.metadata:
                cluster.metadata['order'] = str(cluster_position)
            lane_sort_index += 1

    return graph
