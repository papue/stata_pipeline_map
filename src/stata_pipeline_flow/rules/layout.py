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

    return graph
