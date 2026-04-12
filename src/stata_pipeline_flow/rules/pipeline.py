from __future__ import annotations

from pathlib import Path

from stata_pipeline_flow.config.schema import AppConfig
from stata_pipeline_flow.model.entities import Diagnostic, GraphModel
from stata_pipeline_flow.parser.discovery import discover_project_files
from stata_pipeline_flow.parser.edge_csv import load_edge_csv
from stata_pipeline_flow.parser.stata_extract import build_graph_from_do_files, write_edge_csv
from stata_pipeline_flow.rules.clustering import infer_clusters
from stata_pipeline_flow.rules.cluster_overrides import apply_manual_clusters
from stata_pipeline_flow.rules.layout import apply_layout_config
from stata_pipeline_flow.rules.exclusions import resolve_exclusion_config
from stata_pipeline_flow.rules.version_families import apply_version_family_resolution





def _add_exclusion_ergonomics_diagnostics(graph: GraphModel, config: AppConfig) -> None:
    active_presets = [preset for preset in config.exclusions.presets if preset]
    custom_rules = sum(
        len(values)
        for values in [
            config.exclusions.prefixes,
            config.exclusions.globs,
            config.exclusions.exact_names,
            config.exclusions.exact_paths,
            config.exclusions.folder_names,
            config.exclusions.paths,
            config.exclusions.file_names,
        ]
    )
    if custom_rules and not active_presets:
        graph.add_diagnostic(
            Diagnostic(
                level='info',
                code='exclusion_defaults_not_inherited',
                message='Custom exclusions are active without presets. Default folders such as viewer_output, archive, old, and .git are not excluded unless you add presets or list them explicitly.',
                payload={'custom_rule_count': str(custom_rules)},
            )
        )


def _add_view_relevance_diagnostics(graph: GraphModel, config: AppConfig) -> None:
    view = config.display.view
    irrelevant_messages: list[tuple[str, str]] = []
    if view == 'deliverables':
        irrelevant_messages.append(('show_temporary_outputs', 'display.show_temporary_outputs has no visible effect in deliverables view.'))
    if view in {'scripts_only', 'stage_overview'}:
        irrelevant_messages.append(('show_terminal_outputs', f'display.show_terminal_outputs has no visible effect in {view} view.'))
        irrelevant_messages.append(('show_temporary_outputs', f'display.show_temporary_outputs has no visible effect in {view} view.'))
    if view == 'stage_overview':
        irrelevant_messages.append(('node_label_style', 'display.node_label_style has no visible effect in stage_overview because cluster summary nodes are rendered instead of artifact labels.'))
        irrelevant_messages.append(('label_path_depth', 'display.label_path_depth has no visible effect in stage_overview because cluster summary nodes are rendered instead of artifact labels.'))
        irrelevant_messages.append(('show_extensions', 'display.show_extensions has no visible effect in stage_overview because cluster summary nodes are rendered instead of artifact labels.'))
    for option_name, message in irrelevant_messages:
        graph.add_diagnostic(
            Diagnostic(
                level='info',
                code='display_option_irrelevant',
                message=message,
                payload={'view': view, 'option': option_name},
            )
        )

class PipelineBuilder:
    def __init__(self, config: AppConfig):
        self.config = config

    def build(self, project_root: Path) -> GraphModel:
        effective_exclusions = resolve_exclusion_config(self.config.exclusions)
        scan = discover_project_files(project_root, effective_exclusions, self.config.normalization)
        edge_csv = project_root / self.config.parser.edge_csv_path

        if self.config.parser.prefer_existing_edge_csv and edge_csv.exists():
            graph = load_edge_csv(project_root, edge_csv)
        else:
            graph = build_graph_from_do_files(
                project_root,
                scan.do_files,
                effective_exclusions,
                self.config.parser,
                self.config.normalization,
                self.config.classification,
                self.config.display,
            )
            if self.config.parser.write_edge_csv:
                write_edge_csv(graph, edge_csv)

        graph = apply_version_family_resolution(graph, project_root, self.config.parser.version_families)

        if self.config.clustering.enabled:
            graph = infer_clusters(graph)
        if self.config.clusters:
            graph = apply_manual_clusters(graph, self.config.clusters)
        graph = apply_layout_config(graph, self.config.layout)

        graph.excluded_paths.extend(scan.excluded_files)
        _add_view_relevance_diagnostics(graph, self.config)
        _add_exclusion_ergonomics_diagnostics(graph, self.config)
        if scan.excluded_files:
            graph.add_diagnostic(
                Diagnostic(
                    level='info',
                    code='excluded_files',
                    message=f'Excluded {len(scan.excluded_files)} files during discovery.',
                    payload={'count': str(len(scan.excluded_files))},
                )
            )

        graph.add_diagnostic(
            Diagnostic(
                level='info',
                code='project_scan',
                message='Project discovery completed.',
                payload={
                    'do_files': str(len(scan.do_files)),
                    'input_files': str(len(scan.input_files)),
                    'output_artifacts': str(len(scan.output_artifacts)),
                },
            )
        )
        return graph
