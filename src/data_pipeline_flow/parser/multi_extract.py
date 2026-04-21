"""
Multi-language graph builder.

Extends the Stata-only build_graph_from_do_files() to support Python and R scripts
by dispatching to language-specific parsers via PARSER_REGISTRY.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Callable

from data_pipeline_flow.config.schema import (
    ClassificationConfig,
    ExclusionConfig,
    NormalizationConfig,
    ParserConfig,
)
from data_pipeline_flow.model.entities import Diagnostic, Edge, GraphModel, Node
from data_pipeline_flow.parser.stata_extract import (
    ScriptParseResult,
    READ_COMMANDS as STATA_READ_COMMANDS,
    WRITE_COMMANDS as STATA_WRITE_COMMANDS,
    parse_do_file,
    _is_temporary,
    _add_version_family_diagnostics,
)
from data_pipeline_flow.parser.python_extract import parse_python_file
from data_pipeline_flow.parser.r_extract import parse_r_file
from data_pipeline_flow.rules.exclusions import is_excluded

# ---------------------------------------------------------------------------
# Parser registry
# ---------------------------------------------------------------------------

ParseFunction = Callable[
    [Path, Path, ExclusionConfig, NormalizationConfig, ParserConfig],
    ScriptParseResult,
]

PARSER_REGISTRY: dict[str, ParseFunction] = {
    '.do': parse_do_file,
    '.py': parse_python_file,
    '.r': parse_r_file,
}

# ---------------------------------------------------------------------------
# Language metadata
# ---------------------------------------------------------------------------

def _detect_language(rel_path: str) -> str:
    suffix = Path(rel_path).suffix.lower()
    return {'.do': 'stata', '.py': 'python', '.r': 'r'}.get(suffix, 'unknown')


SCRIPT_CALL_OPERATION: dict[str, str] = {
    'stata': 'do',
    'python': 'import',
    'r': 'source',
}

# ---------------------------------------------------------------------------
# Per-language read/write command sets
# (used to route ParsedEvents into read vs. write buckets)
# ---------------------------------------------------------------------------

_STATA_READ_CMDS: set[str] = set(STATA_READ_COMMANDS.keys())
_STATA_WRITE_CMDS: set[str] = set(STATA_WRITE_COMMANDS.keys())

_PYTHON_READ_CMDS: set[str] = {
    'read_csv', 'read_excel', 'read_parquet', 'read_stata', 'read_json',
    'read_feather', 'read_table', 'read_hdf', 'read_pickle', 'read_orc',
    'np_load', 'np_loadtxt', 'np_genfromtxt',
    'open_read', 'pickle_load', 'json_load', 'yaml_safe_load',
    'runpy',
    'gpd_read_file', 'joblib_load',
}

_PYTHON_WRITE_CMDS: set[str] = {
    'to_csv', 'to_excel', 'to_parquet', 'to_stata', 'to_json',
    'to_feather', 'to_hdf', 'to_pickle', 'to_orc',
    'savefig', 'open_write', 'pickle_dump', 'json_dump',
    'np_save', 'np_savetxt', 'np_savez', 'np_savez_compressed',
    'to_file', 'joblib_dump', 'save_method',
}

_R_READ_CMDS: set[str] = {
    'read_csv', 'read_csv2', 'read_table', 'read_delim', 'readRDS', 'load',
    'read_csv_readr', 'read_csv2_readr', 'read_delim_readr', 'read_rds', 'read_tsv',
    'read_excel', 'read_xls', 'read_xlsx',
    'read_dta', 'read_sas', 'read_spss', 'read_sav',
    'fread', 'read_parquet', 'read_feather', 'fromJSON',
    'st_read', 'st_read_ns', 'read_html',
    'read.xlsx', 'loadWorkbook', 'read.fst', 'read_fst',
}

_R_WRITE_CMDS: set[str] = {
    'write_csv', 'write_csv2', 'write_table', 'saveRDS',
    'write_csv_readr', 'write_csv2_readr', 'write_tsv', 'write_delim', 'write_rds',
    'write_xlsx', 'fwrite',
    'write_dta', 'write_sav', 'write_sas',
    'write_parquet', 'write_feather',
    'saveRDS_kw', 'save_rdata',
    'ggsave', 'ggsave_kw',
    'pdf', 'png', 'svg', 'jpeg', 'tiff',
    'write_json', 'toJSON_write',
    'st_write', 'st_write_ns', 'tmap_save', 'tmap_save_kw',
    'saveWidget', 'saveWidget_kw', 'writeLines', 'writeLines_kw',
    'write.xlsx', 'saveWorkbook', 'write.fst',
}

_LANGUAGE_READ_CMDS: dict[str, set[str]] = {
    'stata': _STATA_READ_CMDS,
    'python': _PYTHON_READ_CMDS,
    'r': _R_READ_CMDS,
}
_LANGUAGE_WRITE_CMDS: dict[str, set[str]] = {
    'stata': _STATA_WRITE_CMDS,
    'python': _PYTHON_WRITE_CMDS,
    'r': _R_WRITE_CMDS,
}

# ---------------------------------------------------------------------------
# Language-agnostic artifact classification
# ---------------------------------------------------------------------------

def _classify_artifact_generic(
    path: str,
    *,
    is_write: bool,
    producer_exists: bool,
    is_placeholder: bool,
    is_temporary: bool,
    deliverable_extensions: set[str],
) -> str:
    suffix = Path(path).suffix.lower()
    if is_placeholder:
        return 'placeholder_artifact'
    if is_temporary:
        return 'temporary'
    if not is_write and not producer_exists:
        return 'reference_input'
    if is_write and suffix in deliverable_extensions:
        return 'deliverable'
    if producer_exists and suffix == '.dta':
        return 'intermediate'
    if producer_exists:
        return 'generated_artifact'
    return 'artifact'

# ---------------------------------------------------------------------------
# Main multi-language graph builder
# ---------------------------------------------------------------------------

def build_graph_from_scripts(
    project_root: Path,
    script_files: list[str],
    exclusions: ExclusionConfig,
    parser_config: ParserConfig,
    normalization: NormalizationConfig,
    classification_config: ClassificationConfig,
    display_config,
) -> GraphModel:
    graph = GraphModel(project_root=str(project_root))
    script_reads: dict[str, set[tuple[str, str, str, str | None]]] = defaultdict(set)
    script_writes: dict[str, set[tuple[str, str, str, str | None]]] = defaultdict(set)
    script_erases: dict[str, set[str]] = defaultdict(set)

    for rel in script_files:
        suffix = Path(rel).suffix.lower()
        parser = PARSER_REGISTRY.get(suffix)
        if parser is None:
            graph.add_diagnostic(Diagnostic(
                level='warning',
                code='unknown_script_type',
                message=f'No parser registered for script: {rel}',
                payload={'path': rel, 'suffix': suffix},
            ))
            continue

        lang = _detect_language(rel)
        path = project_root / rel
        result = parser(project_root, path, exclusions, normalization, parser_config)

        # Script node — includes language metadata
        graph.add_node(Node(
            node_id=rel,
            label=Path(rel).name,
            node_type='script',
            path=rel,
            role='script',
            metadata={'language': lang},
        ))

        for diagnostic in result.global_warnings:
            graph.add_diagnostic(diagnostic)
        for diagnostic in result.excluded_references:
            graph.add_diagnostic(diagnostic)

        call_op = SCRIPT_CALL_OPERATION.get(lang, 'call')
        for child in result.child_scripts:
            child_lang = _detect_language(child)
            graph.add_node(Node(
                node_id=child,
                label=Path(child).name,
                node_type='script',
                path=child,
                role='script',
                metadata={'language': child_lang},
            ))
            graph.add_edge(Edge(
                source=rel,
                target=child,
                operation=call_op,
                kind='script_call',
                visible_label=None,
            ))

        read_cmds = _LANGUAGE_READ_CMDS.get(lang, set())
        write_cmds = _LANGUAGE_WRITE_CMDS.get(lang, set())

        for event in result.events:
            if event.was_absolute:
                graph.add_diagnostic(Diagnostic(
                    level='warning',
                    code='absolute_path_usage',
                    message=f'Absolute path detected in {rel}:{event.line}',
                    payload={'script': rel, 'path': ' | '.join(event.normalized_paths)},
                ))
            if event.resolution_status == 'partial':
                graph.add_diagnostic(Diagnostic(
                    level='info',
                    code='dynamic_path_partial_resolution',
                    message=f'Dynamic path partially resolved in {rel}:{event.line}',
                    payload={
                        'script': rel,
                        'line': str(event.line),
                        'pattern': event.dynamic_pattern or event.raw_path,
                    },
                ))
            elif event.resolution_status != 'full':
                graph.add_diagnostic(Diagnostic(
                    level='warning',
                    code='dynamic_path_unresolved',
                    message=f'Dynamic path unresolved in {rel}:{event.line}',
                    payload={'script': rel, 'line': str(event.line), 'pattern': event.raw_path},
                ))

            target_collection = None
            if event.command in read_cmds:
                target_collection = script_reads[rel]
            elif event.command in write_cmds:
                target_collection = script_writes[rel]
            elif event.command == 'erase':
                script_erases[rel].update(event.normalized_paths)
                continue

            if target_collection is not None:
                for normalized_path in event.normalized_paths:
                    target_collection.add((
                        normalized_path,
                        event.command,
                        event.resolution_status,
                        event.dynamic_pattern,
                    ))

    consumers: dict[str, set[str]] = defaultdict(set)
    producers: dict[str, set[str]] = defaultdict(set)
    erased_paths = {p for paths in script_erases.values() for p in paths}
    for script, reads in script_reads.items():
        for p, _, _, _ in reads:
            consumers[p].add(script)
    for script, writes in script_writes.items():
        for p, _, _, _ in writes:
            producers[p].add(script)

    deliverable_extensions = {
        ext.lower() if ext.startswith('.') else f'.{ext.lower()}'
        for ext in classification_config.deliverable_extensions
    }

    suppressed_internal_only: set[tuple[str, str]] = set()
    if parser_config.suppress_internal_only_writes:
        for script, writes in script_writes.items():
            for p, command, resolution_status, _ in writes:
                if resolution_status != 'full':
                    continue
                if _is_temporary(p, classification_config.temporary_name_patterns, erased_paths):
                    if not display_config.show_temporary_outputs:
                        suppressed_internal_only.add((script, p))
                    continue
                role = _classify_artifact_generic(
                    p,
                    is_write=True,
                    producer_exists=True,
                    is_placeholder=False,
                    is_temporary=False,
                    deliverable_extensions=deliverable_extensions,
                )
                if role != 'deliverable' and consumers.get(p, set()) <= {script}:
                    suppressed_internal_only.add((script, p))
                    if not consumers.get(p):
                        graph.add_diagnostic(Diagnostic(
                            level='info',
                            code='unconsumed_output',
                            message=f'Produced artifact is not consumed downstream: {p}',
                            payload={'path': p},
                        ))

    for script, reads in sorted(script_reads.items()):
        for p, command, resolution_status, pattern in sorted(reads):
            if (script, p) in suppressed_internal_only:
                continue
            is_placeholder = resolution_status != 'full'
            is_temporary = _is_temporary(p, classification_config.temporary_name_patterns, erased_paths)
            role = _classify_artifact_generic(
                p,
                is_write=False,
                producer_exists=bool(producers.get(p)),
                is_placeholder=is_placeholder,
                is_temporary=is_temporary,
                deliverable_extensions=deliverable_extensions,
            )
            node_type = 'artifact_placeholder' if is_placeholder else 'artifact'
            metadata: dict[str, str] = {}
            if pattern:
                metadata['dynamic_pattern'] = pattern
                metadata['resolution_status'] = resolution_status
            graph.add_node(Node(
                node_id=p,
                label=Path(p).name,
                node_type=node_type,
                path=None if is_placeholder else p,
                role=role,
                metadata=metadata,
            ))
            graph.add_edge(Edge(
                source=p,
                target=script,
                operation=command,
                kind=role,
                visible_label=command,
            ))

    visible_temporary_paths: set[str] = set()
    hidden_temporary_paths: set[str] = set()

    for script, writes in sorted(script_writes.items()):
        for p, command, resolution_status, pattern in sorted(writes):
            if (script, p) in suppressed_internal_only:
                continue
            is_placeholder = resolution_status != 'full'
            is_temporary = _is_temporary(p, classification_config.temporary_name_patterns, erased_paths)
            role = _classify_artifact_generic(
                p,
                is_write=True,
                producer_exists=True,
                is_placeholder=is_placeholder,
                is_temporary=is_temporary,
                deliverable_extensions=deliverable_extensions,
            )
            if role == 'temporary' and not display_config.show_temporary_outputs:
                hidden_temporary_paths.add(p)
                continue
            metadata = {}
            if pattern:
                metadata['dynamic_pattern'] = pattern
                metadata['resolution_status'] = resolution_status
            if role == 'temporary':
                visible_temporary_paths.add(p)
                if p in erased_paths:
                    metadata['erased'] = 'true'
            node_type = 'artifact_placeholder' if is_placeholder else 'artifact'
            graph.add_node(Node(
                node_id=p,
                label=Path(p).name,
                node_type=node_type,
                path=None if is_placeholder else p,
                role=role,
                metadata=metadata,
            ))
            graph.add_edge(Edge(
                source=script,
                target=p,
                operation=command,
                kind=role,
                visible_label=command,
            ))

    if hidden_temporary_paths:
        graph.add_diagnostic(Diagnostic(
            level='info',
            code='temporary_outputs_hidden',
            message=f'Hid {len(hidden_temporary_paths)} temporary outputs based on display.show_temporary_outputs=false',
            payload={'count': str(len(hidden_temporary_paths))},
        ))

    if visible_temporary_paths:
        erased_visible = sorted(p for p in visible_temporary_paths if p in erased_paths)
        payload: dict[str, str] = {'count': str(len(visible_temporary_paths))}
        if erased_visible:
            payload['erased_count'] = str(len(erased_visible))
            payload['erased_paths'] = ' | '.join(erased_visible)
        graph.add_diagnostic(Diagnostic(
            level='info',
            code='temporary_outputs_rendered',
            message=f'Rendered {len(visible_temporary_paths)} temporary outputs because display.show_temporary_outputs=true',
            payload=payload,
        ))

    for script, erased in sorted(script_erases.items()):
        for p in sorted(erased):
            graph.add_diagnostic(Diagnostic(
                level='info',
                code='erased_artifact',
                message=f'Artifact erased inside script: {p}',
                payload={'script': script, 'path': p},
            ))

    _add_version_family_diagnostics(graph, project_root, parser_config.version_families.mode)
    graph.excluded_paths.extend(sorted({p for p in script_files if is_excluded(p, exclusions)}))
    return graph
