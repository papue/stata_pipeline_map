"""
Multi-language graph builder.

Extends the Stata-only build_graph_from_do_files() to support Python and R scripts
by dispatching to language-specific parsers via PARSER_REGISTRY.
"""
from __future__ import annotations

import re
from collections import defaultdict, deque
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
from data_pipeline_flow.parser.python_extract import parse_python_file, extract_module_constants
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
    'os_walk',
    # Note: 'fstring_path' is intentionally omitted here.
    # It is routed below using event.is_write so that write-context f-strings
    # produce script → artifact edges instead of artifact → script edges.
}

_PYTHON_WRITE_CMDS: set[str] = {
    'to_csv', 'to_excel', 'to_parquet', 'to_stata', 'to_json',
    'to_feather', 'to_hdf', 'to_pickle', 'to_orc',
    'savefig', 'open_write', 'pickle_dump', 'json_dump',
    'np_save', 'np_savetxt', 'np_savez', 'np_savez_compressed',
    'to_file', 'joblib_dump', 'save_method',
    # pathlib write methods (Fix A)
    'write_text', 'write_bytes',
    # keyword-argument path heuristic (Fix B)
    'kwarg_write',
}

_R_READ_CMDS: set[str] = {
    'read_csv', 'read_csv2', 'read_table', 'read_delim', 'readRDS', 'load',
    'read_csv_readr', 'read_csv2_readr', 'read_delim_readr', 'read_rds', 'read_tsv',
    'read_excel', 'read_xls', 'read_xlsx',
    'read_dta', 'read_sas', 'read_spss', 'read_sav',
    'fread', 'read_parquet', 'read_feather', 'fromJSON',
    'st_read', 'st_read_ns', 'read_html',
    'read.xlsx', 'loadWorkbook', 'read.fst', 'read_fst',
    'list_files',
}

_R_WRITE_CMDS: set[str] = {
    'write_csv', 'write_csv2', 'write_table', 'saveRDS',
    'write_csv_readr', 'write_csv2_readr', 'write_tsv', 'write_delim', 'write_rds',
    'write_xlsx', 'fwrite',
    'write_dta', 'write_sav', 'write_sas',
    'write_parquet', 'write_feather',
    'saveRDS_kw', 'save_rdata',
    'ggsave', 'ggsave_kw',
    'pdf', 'pdf_kw', 'png', 'png_kw', 'svg', 'svg_kw', 'jpeg', 'jpeg_kw', 'tiff', 'tiff_kw',
    'write_json', 'toJSON_write',
    'st_write', 'st_write_ns', 'tmap_save', 'tmap_save_kw',
    'saveWidget', 'saveWidget_kw', 'writeLines', 'writeLines_kw',
    'write.xlsx', 'saveWorkbook', 'write.fst',
    'write_xlsx_kw', 'write_parquet_kw',
    'cat_file', 'message_file',
    'inferred_kwarg',
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

# Presentation-format suffixes that are never demoted from `deliverable` even when
# consumed downstream (plots/documents are almost never read back programmatically).
_PRESENTATION_SUFFIXES: frozenset[str] = frozenset({
    '.png', '.pdf', '.svg', '.doc', '.docx', '.tex', '.ppt', '.pptx',
    '.jpg', '.jpeg', '.tiff', '.eps', '.emf',
})

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
# Python cross-script constant propagation helpers
# ---------------------------------------------------------------------------

_PY_FROM_IMPORT_RE = re.compile(r'^\s*from\s+([\w.]+)\s+import\s+(.+)')
_PY_IMPORT_RE = re.compile(r'^\s*import\s+([\w.]+)')


def _gather_imported_constants(
    py_file: Path,
    project_root: Path,
    module_constants: dict[str, dict[str, str]],
) -> dict[str, str]:
    """Scan *py_file* for ``from <module> import <names>`` and ``import <module>``
    statements that reference project-local modules, and return a merged dict of
    the imported string constants (name → value).

    Only constants that are top-level string literals in the imported module are
    included.  Dynamic values and third-party packages are ignored (no entry in
    *module_constants*).

    *module_constants* maps project-relative module path (e.g. ``"config.py"``)
    to the dict returned by :func:`extract_module_constants`.
    """
    try:
        text = py_file.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return {}

    result: dict[str, str] = {}
    for raw_line in text.splitlines():
        # ``from config import DATA_DIR, OUTPUT_DIR``
        m = _PY_FROM_IMPORT_RE.match(raw_line)
        if m:
            module = m.group(1)
            names_str = m.group(2)
            # Resolve module to a project-relative path (check project root and
            # the script's own directory)
            candidate_path = module.replace('.', '/') + '.py'
            mod_constants: dict[str, str] | None = None
            for base in (project_root, py_file.parent):
                candidate = base / candidate_path
                try:
                    rel = str(candidate.relative_to(project_root)).replace('\\', '/')
                except ValueError:
                    continue
                if rel in module_constants:
                    mod_constants = module_constants[rel]
                    break
            if mod_constants is None:
                continue
            # Parse the imported names (handles aliases: DATA_DIR as DIR)
            for item in names_str.split(','):
                item = item.strip()
                if ' as ' in item:
                    orig, alias = item.split(' as ', 1)
                    orig = orig.strip()
                    alias = alias.strip()
                    if orig in mod_constants:
                        result[alias] = mod_constants[orig]
                        result[orig] = mod_constants[orig]  # also keep original name
                else:
                    if item in mod_constants:
                        result[item] = mod_constants[item]
            continue

        # ``import config`` — makes constants available as ``config.NAME``
        # We inject them as plain NAME too since attribute-access tracking is
        # limited; this helps the simpler cases.
        m2 = _PY_IMPORT_RE.match(raw_line)
        if m2:
            module = m2.group(1)
            candidate_path = module.replace('.', '/') + '.py'
            for base in (project_root, py_file.parent):
                candidate = base / candidate_path
                try:
                    rel = str(candidate.relative_to(project_root)).replace('\\', '/')
                except ValueError:
                    continue
                if rel in module_constants:
                    result.update(module_constants[rel])
                    break

    return result


# ---------------------------------------------------------------------------
# Stata cross-script global propagation helpers
# ---------------------------------------------------------------------------

def _topo_sort_scripts(
    all_scripts: list[str],
    call_edges: dict[str, list[str]],
) -> tuple[list[str], set[tuple[str, str]]]:
    """Return scripts in topological order (parents before children).

    Uses Kahn's algorithm.  Detected back-edges (cycles) are returned as a set
    of (parent, child) pairs so callers can emit diagnostics.
    """
    # Build in-degree from the *known* script set only.
    in_degree: dict[str, int] = {s: 0 for s in all_scripts}
    for parent, children in call_edges.items():
        for child in children:
            if child in in_degree:
                in_degree[child] += 1

    queue: deque[str] = deque(s for s in all_scripts if in_degree[s] == 0)
    order: list[str] = []
    visited: set[str] = set()
    cycle_edges: set[tuple[str, str]] = set()

    while queue:
        node = queue.popleft()
        order.append(node)
        visited.add(node)
        for child in call_edges.get(node, []):
            if child not in in_degree:
                continue
            if child in visited:
                cycle_edges.add((node, child))
                continue
            in_degree[child] -= 1
            if in_degree[child] == 0:
                queue.append(child)

    # Any script not yet visited is part of a cycle; append in arbitrary order.
    for s in all_scripts:
        if s not in visited:
            order.append(s)

    return order, cycle_edges


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

    # -----------------------------------------------------------------------
    # Pass 0 — pre-scan Python files for top-level string constants
    # Used to resolve ``from <module> import NAME`` in other Python scripts.
    # -----------------------------------------------------------------------
    # module_constants maps project-relative path (e.g. "config.py") →
    #   { NAME: "value", ... } for each top-level string constant in that file.
    py_module_constants: dict[str, dict[str, str]] = {}
    for rel in script_files:
        if Path(rel).suffix.lower() == '.py':
            py_file_path = project_root / rel
            constants = extract_module_constants(py_file_path)
            if constants:
                py_module_constants[rel] = constants

    # -----------------------------------------------------------------------
    # Pass 1 — parse every script to build call graph and collect Stata globals
    # -----------------------------------------------------------------------
    # For Stata scripts we need a second pass with inherited globals, so store
    # first-pass results keyed by rel path.
    first_pass_results: dict[str, ScriptParseResult] = {}
    # call_graph maps each Stata parent → list of Stata child rel paths
    stata_call_graph: dict[str, list[str]] = {}
    stata_scripts: list[str] = []
    # call_graph maps each R parent → list of R child rel paths (all lowercase-normalised)
    r_call_graph: dict[str, list[str]] = {}
    r_scripts: list[str] = []
    # mapping from lowercase-normalised rel path → original case rel path (for filesystem access)
    r_norm_to_orig: dict[str, str] = {}

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
        if lang == 'python' and py_module_constants:
            imported = _gather_imported_constants(path, project_root, py_module_constants)
            result = parse_python_file(
                project_root, path, exclusions, normalization, parser_config,
                imported_constants=imported if imported else None,
            )
        else:
            result = parser(project_root, path, exclusions, normalization, parser_config)
        first_pass_results[rel] = result

        if lang == 'stata':
            stata_scripts.append(rel)
            stata_call_graph[rel] = [c for c in result.child_scripts if Path(c).suffix.lower() == '.do']
        elif lang == 'r':
            # Normalise to lowercase so child_scripts (already normalised by parse_r_file
            # via normalize_token) match the keys we store here.
            r_norm = rel.lower()
            if r_norm not in r_scripts:
                r_scripts.append(r_norm)
            r_norm_to_orig[r_norm] = rel
            # child_scripts are already lowercase-normalised by normalize_token inside parse_r_file
            r_call_graph[r_norm] = [c for c in result.child_scripts if Path(c).suffix.lower() == '.r']
            # Re-key first_pass_results with the normalised key so second-pass lookup works
            first_pass_results[r_norm] = result

    # -----------------------------------------------------------------------
    # Pass 2 — re-parse Stata scripts in topological order with inherited globals
    # -----------------------------------------------------------------------
    topo_order, cycle_edges = _topo_sort_scripts(stata_scripts, stata_call_graph)
    for parent, child in cycle_edges:
        graph.add_diagnostic(Diagnostic(
            level='warning',
            code='cycle_detected',
            message=f'Cycle detected in Stata script call graph: {parent} → {child}',
            payload={'parent': parent, 'child': child},
        ))

    # accumulated_globals[rel] = merged globals available to this script's children
    accumulated_globals: dict[str, dict[str, str]] = {}
    # second_pass_results replaces first_pass_results for Stata scripts only
    second_pass_results: dict[str, ScriptParseResult] = {}

    for rel in topo_order:
        if rel not in stata_call_graph:
            continue  # not a Stata script or not in known set

        # Collect inherited globals from all parents in call graph
        inherited: dict[str, str] = {}
        for parent in stata_scripts:
            if rel in stata_call_graph.get(parent, []):
                # Merge parent's accumulated globals (grandparent → parent) first,
                # then parent's own globals — closer caller wins on conflict.
                parent_accumulated = accumulated_globals.get(parent, {})
                inherited.update(parent_accumulated)

        path = project_root / rel
        result2 = parse_do_file(
            project_root,
            path,
            exclusions,
            normalization,
            parser_config,
            inherited_globals=inherited if inherited else None,
        )
        second_pass_results[rel] = result2
        # This script's accumulated globals = inherited + own definitions (own wins)
        merged = dict(inherited)
        merged.update(result2.globals_map)
        accumulated_globals[rel] = merged

    # -----------------------------------------------------------------------
    # Pass 2b — re-parse R scripts in topological order with inherited vars
    # -----------------------------------------------------------------------
    r_topo_order, r_cycle_edges = _topo_sort_scripts(r_scripts, r_call_graph)
    for parent, child in r_cycle_edges:
        graph.add_diagnostic(Diagnostic(
            level='warning',
            code='cycle_detected',
            message=f'Cycle detected in R script call graph: {parent} → {child}',
            payload={'parent': parent, 'child': child},
        ))

    # accumulated_r_vars[rel] = merged vars available to this script's children
    accumulated_r_vars: dict[str, dict[str, str]] = {}
    # r_second_pass_results replaces first_pass_results for R scripts only
    r_second_pass_results: dict[str, ScriptParseResult] = {}

    for rel in r_topo_order:
        if rel not in r_call_graph:
            continue  # not an R script or not in known set

        # Collect inherited vars from all parents in R call graph
        inherited_r: dict[str, str] = {}
        for parent in r_scripts:
            if rel in r_call_graph.get(parent, []):
                # Merge parent's accumulated vars (grandparent → parent) first,
                # then parent's own vars — closer caller wins on conflict.
                parent_accumulated = accumulated_r_vars.get(parent, {})
                inherited_r.update(parent_accumulated)

        # Use the original case path for filesystem access (R files often use .R extension)
        orig_rel = r_norm_to_orig.get(rel, rel)
        path = project_root / orig_rel
        result2 = parse_r_file(
            project_root,
            path,
            exclusions,
            normalization,
            parser_config,
            inherited_vars=inherited_r if inherited_r else None,
        )
        r_second_pass_results[rel] = result2
        # This script's accumulated vars = inherited + own definitions (own wins)
        merged_r = dict(inherited_r)
        merged_r.update(result2.globals_map)
        accumulated_r_vars[rel] = merged_r

    # -----------------------------------------------------------------------
    # Main processing loop — use second-pass results for Stata/R, first-pass otherwise
    # -----------------------------------------------------------------------
    for rel in script_files:
        suffix = Path(rel).suffix.lower()
        if suffix not in PARSER_REGISTRY:
            continue  # already diagnosed in pass 1

        lang = _detect_language(rel)
        if lang == 'stata' and rel in second_pass_results:
            result = second_pass_results[rel]
        elif lang == 'r' and rel.lower() in r_second_pass_results:
            result = r_second_pass_results[rel.lower()]
        elif rel in first_pass_results:
            result = first_pass_results[rel]
        else:
            continue

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
            # For Python imports and R source() the data-flow direction is reversed:
            # the imported/sourced module (child) feeds *into* the importing script (rel).
            # R's source() executes the helper in the calling environment, making
            # functions/objects from the helper available to the caller — semantically
            # identical to Python import.
            # For Stata `do`, the caller drives sequential execution so the conventional
            # caller → child direction is kept.
            if lang in ('python', 'r'):
                edge_source, edge_target = child, rel
            else:
                edge_source, edge_target = rel, child
            graph.add_edge(Edge(
                source=edge_source,
                target=edge_target,
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
            if event.command == 'fstring_path':
                # Route using the is_write flag set by python_extract.py so that
                # write-context f-strings produce script → artifact edges.
                if event.is_write:
                    target_collection = script_writes[rel]
                else:
                    target_collection = script_reads[rel]
            elif event.command in read_cmds:
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
                # Demote deliverable → intermediate when other scripts consume the file.
                # Presentation formats (.png, .pdf, .svg, etc.) are excluded from
                # this demotion because they are almost never read back programmatically.
                if role == 'deliverable' and Path(p).suffix.lower() not in _PRESENTATION_SUFFIXES:
                    if bool(consumers.get(p, set()) - {script}):
                        role = 'intermediate'
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
            # Demote deliverable → intermediate when other scripts consume the file.
            # Presentation formats (.png, .pdf, .svg, etc.) are excluded from
            # this demotion because they are almost never read back programmatically.
            if role == 'deliverable' and Path(p).suffix.lower() not in _PRESENTATION_SUFFIXES:
                if bool(consumers.get(p, set()) - {script}):
                    role = 'intermediate'
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
            # The reads loop runs first and may have already stored a weaker role
            # (e.g. `generated_artifact`) via setdefault.  When the write loop now
            # determines a more specific role (`intermediate` or `deliverable`),
            # override the existing node role so the two representations stay consistent.
            _ROLE_PRIORITY = {'deliverable': 3, 'intermediate': 2, 'generated_artifact': 1}
            existing = graph.nodes.get(p)
            if existing is not None and existing.role != role:
                existing_prio = _ROLE_PRIORITY.get(existing.role, 0)
                write_prio = _ROLE_PRIORITY.get(role, 0)
                if write_prio > existing_prio:
                    graph.nodes[p] = Node(
                        node_id=p,
                        label=existing.label,
                        node_type=existing.node_type,
                        path=existing.path,
                        role=role,
                        metadata=existing.metadata,
                    )
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
