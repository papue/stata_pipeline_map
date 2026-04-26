from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
import csv
import itertools
import re

from data_pipeline_flow.config.schema import ClassificationConfig, ExclusionConfig, NormalizationConfig, ParserConfig
from data_pipeline_flow.model.entities import Diagnostic, Edge, GraphModel, Node
from data_pipeline_flow.model.normalize import normalize_token, to_project_relative
from data_pipeline_flow.rules.exclusions import is_excluded

GLOBAL_RE = re.compile(r'^\s*global\s+(\w+)\s+(.+?)\s*$', re.I)
LOCAL_RE = re.compile(r'^\s*local\s+(\w+)\s+(.+?)\s*$', re.I)
LOCAL_COMPUTED_RE = re.compile(r'^\s*local\s+(\w+)\s*=\s*(.+?)\s*$', re.I)
FOREACH_RE = re.compile(r'^\s*foreach\s+(\w+)\s+(?:in|of\s+local)\s+(.+?)\s*\{\s*$', re.I)
FORVALUES_RE = re.compile(r'^\s*forvalues\s+(\w+)\s*=\s*(-?\d+)\s*/\s*(-?\d+)\s*\{\s*$', re.I)
_PATH = r'"([^"]+)"|([^\s,]+\.[^\s,]+)'
DO_RE = re.compile(r'\bdo\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
USE_RE = re.compile(r'\buse\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
SAVE_RE = re.compile(r'\bsave\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
IMPORT_RE = re.compile(r'\bimport\s+(?:delimited|excel)\s+(?:using\s+)?(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
EXPORT_DELIMITED_RE = re.compile(r'\bexport\s+delimited\s+(?:using\s+)?(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
INSHEET_RE = re.compile(r'\binsheet\s+(?:using\s+)?(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
EXPORT_EXCEL_RE = re.compile(r'\bexport\s+excel\s+using\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
GRAPH_EXPORT_RE = re.compile(r'\bgraph\s+export\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
ESTIMATES_SAVE_RE = re.compile(r'\bestimates\s+save\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
PUTEXCEL_SET_RE = re.compile(r'\bputexcel\s+set\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
OUTSHEET_RE = re.compile(r'\boutsheet\s+(?:using\s+)?(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
LOG_USING_RE = re.compile(r'\blog\s+using\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
ESTTAB_RE = re.compile(r'\besttab\b[^\n]*?\busing\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
OUTREG2_RE = re.compile(r'\boutreg2\b[^\n]*?\busing\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
APPEND_RE = re.compile(r'\bappend\s+using\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
MERGE_RE = re.compile(r'\bmerge\s+[^\n]*?using\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
CROSS_RE = re.compile(r'\bcross\s+using\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
ERASE_RE = re.compile(r'\berase\s+(?:"([^"]+)"|([^\s,]+\.[^\s,]+))', re.I)
MACRO_TOKEN_RE = re.compile(r"`([^']+)'")
DOLLAR_GLOBAL_RE = re.compile(r'\$\{(\w+)\}|\$(\w+)')
VERSION_TOKEN_RE = re.compile(r'(?i)(?:_v\d+|_(?:qc|pp|final|draft))(?=\.[^.]+$)')

READ_COMMANDS = {
    'use': USE_RE,
    'import': IMPORT_RE,
    'insheet': INSHEET_RE,
    'append': APPEND_RE,
    'merge': MERGE_RE,
    'cross': CROSS_RE,
}
WRITE_COMMANDS = {
    'save': SAVE_RE,
    'export_delimited': EXPORT_DELIMITED_RE,
    'export_excel': EXPORT_EXCEL_RE,
    'graph_export': GRAPH_EXPORT_RE,
    'estimates_save': ESTIMATES_SAVE_RE,
    'putexcel_set': PUTEXCEL_SET_RE,
    'outsheet': OUTSHEET_RE,
    'log_using': LOG_USING_RE,
    'esttab': ESTTAB_RE,
    'outreg2': OUTREG2_RE,
}


@dataclass(slots=True)
class ParsedEvent:
    script: str
    line: int
    command: str
    raw_path: str
    normalized_paths: list[str]
    was_absolute: bool
    resolution_status: str = 'full'
    dynamic_pattern: str | None = None


@dataclass(slots=True)
class ScriptParseResult:
    events: list[ParsedEvent]
    child_scripts: list[str]
    global_warnings: list[Diagnostic]
    excluded_references: list[Diagnostic] = field(default_factory=list)


@dataclass(slots=True)
class LoopFrame:
    variable: str
    values: list[str]


def _join_stata_continuations(text: str) -> str:
    """Join lines ending with /// (Stata line continuation) before any other parsing."""
    lines = text.splitlines()
    result, i = [], 0
    while i < len(lines):
        line = lines[i]
        while line.rstrip().endswith('///') and i + 1 < len(lines):
            line = line.rstrip()[:-3].rstrip() + ' ' + lines[i + 1].lstrip()
            i += 1
        result.append(line)
        i += 1
    return '\n'.join(result)


def _strip_quotes(text: str) -> str:
    value = text.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def expand(path_expr: str, globals_map: dict[str, str]) -> str:
    path = path_expr
    changed = True
    while changed:
        changed = False
        for key, value in globals_map.items():
            for token in (f'${{{key}}}', f'${key}'):
                if token in path:
                    path = path.replace(token, value)
                    changed = True
    return path


_INLINE_BLOCK_COMMENT_RE = re.compile(r'/\*.*?\*/', re.DOTALL)
_INLINE_LINE_COMMENT_RE = re.compile(r'\s*//.*$')


def _strip_inline_comments(text: str) -> str:
    """Remove /* ... */ block comments and // end-of-line comments from a string."""
    text = _INLINE_BLOCK_COMMENT_RE.sub('', text)
    text = _INLINE_LINE_COMMENT_RE.sub('', text)
    return text.strip()


def _collect_local_values(raw_value: str) -> list[str]:
    cleaned = _strip_quotes(_strip_inline_comments(raw_value))
    return [piece for piece in cleaned.split() if piece]


def _resolve_dynamic_path(
    path_expr: str,
    globals_map: dict[str, str],
    local_map: dict[str, list[str]],
    loop_stack: list[LoopFrame],
    placeholder_token: str,
) -> tuple[list[str], str, str | None]:
    expanded = expand(path_expr, globals_map)
    env: dict[str, list[str]] = {key: values[:] for key, values in local_map.items()}
    for frame in loop_stack:
        env[frame.variable] = frame.values[:]

    # Check for unresolved ${macro} or $macro global references remaining after expand().
    # Before marking partial, try resolving them from locals (dollar-form local references).
    dollar_matches = DOLLAR_GLOBAL_RE.findall(expanded)
    if dollar_matches:
        # First attempt: substitute from env (locals + loop vars) for any dollar-form refs
        # that expand() missed because it only consults globals_map.
        still_expanded = expanded
        still_unresolved = []
        for braced, bare in dollar_matches:
            name = braced or bare
            if name in env and len(env[name]) == 1:
                # Single-valued local: substitute directly
                still_expanded = still_expanded.replace(f'${{{name}}}', env[name][0])
                still_expanded = re.sub(rf'\${re.escape(name)}(?!\w)', env[name][0], still_expanded)
            else:
                still_unresolved.append((braced, bare))
        # Re-check: any remaining unresolved dollar refs?
        remaining_dollar = DOLLAR_GLOBAL_RE.findall(still_expanded)
        if remaining_dollar:
            # Still partial — convert remaining unresolved refs to placeholders
            placeholder = still_expanded
            for braced, bare in remaining_dollar:
                name = braced or bare
                placeholder = placeholder.replace(f'${{{name}}}', f'{{{name}}}')
                placeholder = re.sub(rf'\${re.escape(name)}(?!\w)', f'{{{name}}}', placeholder)
            return [placeholder], 'partial', placeholder
        # All dollar refs resolved via locals — continue with macro token resolution
        expanded = still_expanded

    tokens = MACRO_TOKEN_RE.findall(expanded)
    if not tokens:
        return [expanded], 'full', None

    missing = [token for token in tokens if token not in env]
    if missing:
        placeholder = expanded
        for token in sorted(set(missing)):
            placeholder = placeholder.replace(f"`{token}'", f'{{{token}}}')
        for token in sorted(set(tokens) - set(missing)):
            values = env[token]
            if len(values) == 1:
                placeholder = placeholder.replace(f"`{token}'", values[0])
            else:
                placeholder = placeholder.replace(f"`{token}'", f'{{{token}}}')
        return [placeholder.replace('{}', placeholder_token)], 'partial', placeholder

    unique_tokens: list[str] = []
    for token in tokens:
        if token not in unique_tokens:
            unique_tokens.append(token)

    expansions: list[str] = []
    for combination in itertools.product(*(env[token] for token in unique_tokens)):
        current = expanded
        for token, replacement in zip(unique_tokens, combination):
            current = current.replace(f"`{token}'", replacement)
        expansions.append(current)

    # Multi-pass: resolve nested local/global references up to 3 total passes.
    # After substituting locals, remaining values may contain:
    #   - more local refs (``nested_local'')
    #   - global refs that the local value carried ($global embedded in local value)
    for _pass in range(2):  # up to 2 additional passes (3 total)
        next_pass: list[str] = []
        any_changed = False
        for path_str in expansions:
            # First re-expand any global refs that surfaced after local substitution
            re_expanded = expand(path_str, globals_map)
            if re_expanded != path_str:
                any_changed = True
            # Then resolve any remaining local tokens
            nested_tokens = MACRO_TOKEN_RE.findall(re_expanded)
            if not nested_tokens:
                next_pass.append(re_expanded)
                continue
            nested_missing = [t for t in nested_tokens if t not in env]
            if nested_missing:
                # Some still unresolved — keep as partial
                next_pass.append(re_expanded)
                continue
            nested_unique: list[str] = []
            for token in nested_tokens:
                if token not in nested_unique:
                    nested_unique.append(token)
            for combination2 in itertools.product(*(env[token] for token in nested_unique)):
                current2 = re_expanded
                for token, replacement in zip(nested_unique, combination2):
                    current2 = current2.replace(f"`{token}'", replacement)
                next_pass.append(current2)
                any_changed = True
        expansions = next_pass
        if not any_changed:
            break

    # Check for any remaining unresolved global/local refs after all passes.
    # Convert any remaining unresolved tokens to {token} placeholder form.
    final_pass: list[str] = []
    has_partial = False
    for path_str in expansions:
        remaining_dollar = DOLLAR_GLOBAL_RE.findall(path_str)
        if remaining_dollar:
            has_partial = True
            for braced, bare in remaining_dollar:
                name = braced or bare
                path_str = path_str.replace(f'${{{name}}}', f'{{{name}}}')
                path_str = re.sub(rf'\${re.escape(name)}(?!\w)', f'{{{name}}}', path_str)
        remaining_local = MACRO_TOKEN_RE.findall(path_str)
        unresolved_local = [t for t in remaining_local if t not in env]
        if unresolved_local:
            has_partial = True
            for token in sorted(set(unresolved_local)):
                path_str = path_str.replace(f'`{token}\'', f'{{{token}}}')
        # Normalize backslashes to forward slashes after full substitution
        path_str = path_str.replace('\\', '/')
        final_pass.append(path_str)

    if has_partial:
        return final_pass, 'partial', final_pass[0] if final_pass else None

    deduped = list(dict.fromkeys(final_pass))
    return deduped, 'full', None


def _classify_artifact(
    path: str,
    command: str,
    *,
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
    if suffix in {'.dta', '.csv', '.xlsx'} and not producer_exists and command in {'use', 'import', 'append', 'merge', 'cross'}:
        return 'reference_input'
    if suffix in deliverable_extensions and command in WRITE_COMMANDS:
        return 'deliverable'
    if producer_exists and suffix == '.dta':
        return 'intermediate'
    if producer_exists:
        return 'generated_artifact'
    return 'artifact'


def _excluded_reference(rel_script: str, line: int, command: str, normalized_path: str) -> Diagnostic:
    return Diagnostic(
        level='info',
        code='excluded_reference',
        message=f'Excluded path omitted from graph at {rel_script}:{line} ({command}): {normalized_path}',
        payload={'script': rel_script, 'line': str(line), 'command': command, 'path': normalized_path},
    )


_BARE_DIRECTORY_RE = re.compile(r'^[./\\]*$')


def _is_bare_directory(path: str) -> bool:
    """Return True if the path resolves to a bare directory marker (e.g. '.', '/', '\\')
    with no meaningful file component. Such paths should be discarded to avoid spurious nodes."""
    return bool(_BARE_DIRECTORY_RE.match(path))


def _path_group(m: re.Match) -> str:
    """Return the captured path from a two-group regex (quoted | unquoted)."""
    return m.group(1) if m.group(1) is not None else m.group(2)


def _resolve_script_relative(do_file: Path, expanded: str) -> str:
    """If a path contains '..' and is not absolute, resolve it relative to the
    script's directory so that '../data/x.dta' from 'scripts/analyze.do' maps
    to 'data/x.dta' rather than staying as '../data/x.dta'."""
    if '..' in expanded and not Path(expanded).is_absolute():
        return str((do_file.parent / expanded).resolve())
    return expanded


def parse_do_file(project_root: Path, do_file: Path, exclusions: ExclusionConfig, normalization: NormalizationConfig, parser_config: ParserConfig) -> ScriptParseResult:
    globals_map: dict[str, str] = {}
    local_map: dict[str, list[str]] = {}
    loop_stack: list[LoopFrame] = []
    events: list[ParsedEvent] = []
    child_scripts: list[str] = []
    global_warnings: list[Diagnostic] = []
    excluded_references: list[Diagnostic] = []
    rel_script, _ = to_project_relative(project_root, do_file, normalization)
    rel_script = normalize_token(rel_script)

    try:
        file_text = do_file.read_text(encoding='utf-8')
    except UnicodeDecodeError:
        global_warnings.append(
            Diagnostic(
                level='warning',
                code='file_encoding_error',
                message=f'Could not decode {rel_script} as UTF-8; file skipped.',
                payload={'script': rel_script},
            )
        )
        return ScriptParseResult(
            events=[],
            child_scripts=[],
            global_warnings=global_warnings,
            excluded_references=[],
        )

    # BUG-1: Join /// line continuations before any other parsing
    file_text = _join_stata_continuations(file_text)

    # BUG-2/BUG-3: Pre-seed Stata system constants as locals
    # c(pwd) approximated by "." (project root); c(current_do_file) by the script path
    local_map['c(pwd)'] = ['.']
    local_map['c(current_do_file)'] = [str(do_file)]

    for i, line in enumerate(file_text.splitlines(), start=1):
        stripped = line.strip()
        if stripped == '}' and loop_stack:
            loop_stack.pop()
            continue

        g = GLOBAL_RE.search(line)
        if g:
            raw_val = _strip_quotes(g.group(2))
            expanded = expand(raw_val, globals_map)
            # BUG-8: Preserve trailing slash so that "${ddir}file.dta" concatenates correctly.
            # We store the normalized form but re-append the slash if the original ended with one.
            trailing_slash = expanded.endswith('/') or expanded.endswith('\\')
            norm, was_absolute = to_project_relative(project_root, expanded, normalization)
            if trailing_slash and not norm.endswith('/'):
                norm = norm + '/'
            globals_map[g.group(1)] = norm
            if was_absolute:
                global_warnings.append(
                    Diagnostic(
                        level='warning',
                        code='absolute_path_usage',
                        message=f'Absolute path detected in global defined at {rel_script}:{i}',
                        payload={'script': rel_script, 'path': norm},
                    )
                )
            continue

        # BUG-3: Detect computed local assignments (local name = expr(...))
        # Function calls produce garbage if split on whitespace; store placeholder instead.
        computed = LOCAL_COMPUTED_RE.search(line)
        if computed:
            rhs = computed.group(2).strip()
            # If RHS contains parentheses (function call) or unresolvable system references,
            # store a single opaque placeholder to avoid garbage path expansion.
            if '(' in rhs:
                local_map[computed.group(1)] = [parser_config.dynamic_paths.placeholder_token]
            else:
                local_map[computed.group(1)] = _collect_local_values(rhs)
            continue

        local = LOCAL_RE.search(line)
        if local:
            local_map[local.group(1)] = _collect_local_values(local.group(2))
            continue

        foreach = FOREACH_RE.search(line)
        if foreach:
            raw_values = foreach.group(2).strip()
            if raw_values in local_map:
                loop_values = local_map[raw_values][:]
            else:
                loop_values = _collect_local_values(raw_values)
            loop_stack.append(LoopFrame(variable=foreach.group(1), values=loop_values))
            continue

        forvalues = FORVALUES_RE.search(line)
        if forvalues:
            start = int(forvalues.group(2))
            end = int(forvalues.group(3))
            step = 1 if end >= start else -1
            values = [str(value) for value in range(start, end + step, step)]
            loop_stack.append(LoopFrame(variable=forvalues.group(1), values=values))
            continue

        d = DO_RE.search(line)
        if d:
            expansions, _, _ = _resolve_dynamic_path(_path_group(d), globals_map, local_map, loop_stack, parser_config.dynamic_paths.placeholder_token)
            for expanded in expansions:
                norm, _ = to_project_relative(project_root, _resolve_script_relative(do_file, expanded), normalization)
                norm = normalize_token(norm)
                if is_excluded(norm, exclusions):
                    excluded_references.append(_excluded_reference(rel_script, i, 'do', norm))
                else:
                    child_scripts.append(norm)
            continue

        matched = False
        for command, regex in READ_COMMANDS.items():
            m = regex.search(line)
            if not m:
                continue
            raw_path = _path_group(m)
            expansions, resolution_status, pattern = _resolve_dynamic_path(raw_path, globals_map, local_map, loop_stack, parser_config.dynamic_paths.placeholder_token)
            normalized_paths: list[str] = []
            any_absolute = False
            for expanded in expansions:
                # Check if path was originally absolute BEFORE _resolve_script_relative
                # converts relative ../paths to absolute system paths (false positive prevention)
                originally_absolute = Path(expanded).is_absolute() or expanded.startswith('/') or expanded.startswith('\\\\')
                resolved = _resolve_script_relative(do_file, expanded)
                norm, was_absolute = to_project_relative(project_root, resolved, normalization)
                norm = normalize_token(norm)
                # Fix C: discard paths that reduce to a bare directory marker (e.g. ".", "/")
                if _is_bare_directory(norm):
                    continue
                any_absolute = any_absolute or (was_absolute and originally_absolute)
                if is_excluded(norm, exclusions):
                    excluded_references.append(_excluded_reference(rel_script, i, command, norm))
                else:
                    normalized_paths.append(norm)
            if normalized_paths:
                events.append(ParsedEvent(rel_script, i, command, raw_path, normalized_paths, any_absolute, resolution_status, pattern))
            matched = True
            break
        if matched:
            continue

        for command, regex in WRITE_COMMANDS.items():
            m = regex.search(line)
            if not m:
                continue
            raw_path = _path_group(m)
            expansions, resolution_status, pattern = _resolve_dynamic_path(raw_path, globals_map, local_map, loop_stack, parser_config.dynamic_paths.placeholder_token)
            normalized_paths: list[str] = []
            any_absolute = False
            for expanded in expansions:
                # Check if path was originally absolute BEFORE _resolve_script_relative
                # converts relative ../paths to absolute system paths (false positive prevention)
                originally_absolute = Path(expanded).is_absolute() or expanded.startswith('/') or expanded.startswith('\\\\')
                resolved = _resolve_script_relative(do_file, expanded)
                norm, was_absolute = to_project_relative(project_root, resolved, normalization)
                norm = normalize_token(norm)
                # Fix C: discard paths that reduce to a bare directory marker (e.g. ".", "/")
                if _is_bare_directory(norm):
                    continue
                any_absolute = any_absolute or (was_absolute and originally_absolute)
                if is_excluded(norm, exclusions):
                    excluded_references.append(_excluded_reference(rel_script, i, command, norm))
                else:
                    normalized_paths.append(norm)
            if normalized_paths:
                events.append(ParsedEvent(rel_script, i, command, raw_path, normalized_paths, any_absolute, resolution_status, pattern))
            matched = True
            break
        if matched:
            continue

        m = ERASE_RE.search(line)
        if m:
            raw_path = _path_group(m)
            expansions, _, _ = _resolve_dynamic_path(raw_path, globals_map, local_map, loop_stack, parser_config.dynamic_paths.placeholder_token)
            for expanded in expansions:
                norm, was_absolute = to_project_relative(project_root, expanded, normalization)
                norm = normalize_token(norm)
                if is_excluded(norm, exclusions):
                    excluded_references.append(_excluded_reference(rel_script, i, 'erase', norm))
                else:
                    events.append(ParsedEvent(rel_script, i, 'erase', raw_path, [norm], was_absolute))

    return ScriptParseResult(
        events=events,
        child_scripts=child_scripts,
        global_warnings=global_warnings,
        excluded_references=excluded_references,
    )


def _is_temporary(path: str, temporary_name_patterns: list[str], erased_paths: set[str]) -> bool:
    lowered = path.lower()
    basename = Path(path).name.lower()
    if path in erased_paths:
        return True
    return any(pattern.lower() in lowered or pattern.lower() in basename for pattern in temporary_name_patterns)


def _version_family_key(path: str) -> str | None:
    file_path = Path(path)
    normalized_name = VERSION_TOKEN_RE.sub('', file_path.name)
    if normalized_name == file_path.name:
        return None
    return str(Path(file_path.parent) / normalized_name)


def _add_version_family_diagnostics(graph: GraphModel, project_root: Path, version_mode: str) -> None:
    families: dict[str, list[str]] = defaultdict(list)
    for node in graph.nodes.values():
        if node.node_type not in {'artifact', 'artifact_placeholder'} or node.path is None:
            continue
        family_key = _version_family_key(node.path)
        if family_key:
            families[family_key].append(node.path)

    for family_key, members in sorted(families.items()):
        unique_members = sorted(set(members))
        if len(unique_members) < 2:
            continue
        graph.add_diagnostic(
            Diagnostic(
                level='info',
                code='version_family_detected',
                message=f'Likely versioned file family detected: {family_key}',
                payload={'family': family_key, 'members': ' | '.join(unique_members), 'mode': version_mode},
            )
        )
        mtimes = []
        for member in unique_members:
            path = project_root / member
            if path.exists():
                mtimes.append((path.stat().st_mtime, member))
        if len(mtimes) >= 2:
            mtimes.sort(reverse=True)
            if mtimes[0][0] == mtimes[1][0]:
                graph.add_diagnostic(
                    Diagnostic(
                        level='warning',
                        code='version_family_ambiguous',
                        message=f'Version family tie on modified time: {family_key}',
                        payload={'family': family_key, 'members': ' | '.join(unique_members)},
                    )
                )


def build_graph_from_do_files(
    project_root: Path,
    do_files: list[str],
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

    for rel in do_files:
        path = project_root / rel
        result = parse_do_file(project_root, path, exclusions, normalization, parser_config)
        graph.add_node(Node(node_id=rel, label=Path(rel).name, node_type='script', path=rel, role='script'))
        for diagnostic in result.global_warnings:
            graph.add_diagnostic(diagnostic)
        for diagnostic in result.excluded_references:
            graph.add_diagnostic(diagnostic)
        for child in result.child_scripts:
            graph.add_node(Node(node_id=child, label=Path(child).name, node_type='script', path=child, role='script'))
            graph.add_edge(Edge(source=rel, target=child, operation='do', kind='script_call', visible_label=None))
        for event in result.events:
            if event.was_absolute:
                graph.add_diagnostic(
                    Diagnostic(
                        level='warning',
                        code='absolute_path_usage',
                        message=f'Absolute path detected in {rel}:{event.line}',
                        payload={'script': rel, 'path': ' | '.join(event.normalized_paths)},
                    )
                )
            if event.resolution_status == 'partial':
                graph.add_diagnostic(
                    Diagnostic(
                        level='info',
                        code='dynamic_path_partial_resolution',
                        message=f'Dynamic path partially resolved in {rel}:{event.line}',
                        payload={'script': rel, 'line': str(event.line), 'pattern': event.dynamic_pattern or event.raw_path},
                    )
                )
            elif event.resolution_status != 'full':
                graph.add_diagnostic(
                    Diagnostic(
                        level='warning',
                        code='dynamic_path_unresolved',
                        message=f'Dynamic path unresolved in {rel}:{event.line}',
                        payload={'script': rel, 'line': str(event.line), 'pattern': event.raw_path},
                    )
                )

            target_collection = None
            if event.command in READ_COMMANDS:
                target_collection = script_reads[rel]
            elif event.command in WRITE_COMMANDS:
                target_collection = script_writes[rel]
            elif event.command == 'erase':
                script_erases[rel].update(event.normalized_paths)
                continue
            if target_collection is not None:
                for normalized_path in event.normalized_paths:
                    target_collection.add((normalized_path, event.command, event.resolution_status, event.dynamic_pattern))

    consumers: dict[str, set[str]] = defaultdict(set)
    producers: dict[str, set[str]] = defaultdict(set)
    erased_paths = {path for paths in script_erases.values() for path in paths}
    for script, reads in script_reads.items():
        for p, _, _, _ in reads:
            consumers[p].add(script)
    for script, writes in script_writes.items():
        for p, _, _, _ in writes:
            producers[p].add(script)

    deliverable_extensions = {ext.lower() if ext.startswith('.') else f'.{ext.lower()}' for ext in classification_config.deliverable_extensions}

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
                role = _classify_artifact(
                    p,
                    command,
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
            role = _classify_artifact(
                p,
                command,
                producer_exists=bool(producers.get(p)),
                is_placeholder=is_placeholder,
                is_temporary=is_temporary,
                deliverable_extensions=deliverable_extensions,
            )
            node_type = 'artifact_placeholder' if is_placeholder else 'artifact'
            metadata = {}
            if pattern:
                metadata['dynamic_pattern'] = pattern
                metadata['resolution_status'] = resolution_status
            graph.add_node(Node(node_id=p, label=Path(p).name, node_type=node_type, path=None if is_placeholder else p, role=role, metadata=metadata))
            graph.add_edge(Edge(source=p, target=script, operation=command, kind=role, visible_label=command))

    visible_temporary_paths: set[str] = set()
    hidden_temporary_paths: set[str] = set()

    for script, writes in sorted(script_writes.items()):
        for p, command, resolution_status, pattern in sorted(writes):
            if (script, p) in suppressed_internal_only:
                continue
            is_placeholder = resolution_status != 'full'
            is_temporary = _is_temporary(p, classification_config.temporary_name_patterns, erased_paths)
            role = _classify_artifact(
                p,
                command,
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
            graph.add_node(Node(node_id=p, label=Path(p).name, node_type=node_type, path=None if is_placeholder else p, role=role, metadata=metadata))
            graph.add_edge(Edge(source=script, target=p, operation=command, kind=role, visible_label=command))

    if hidden_temporary_paths:
        graph.add_diagnostic(
            Diagnostic(
                level='info',
                code='temporary_outputs_hidden',
                message=f'Hid {len(hidden_temporary_paths)} temporary outputs based on display.show_temporary_outputs=false',
                payload={'count': str(len(hidden_temporary_paths))},
            )
        )

    if visible_temporary_paths:
        erased_visible = sorted(path for path in visible_temporary_paths if path in erased_paths)
        payload = {'count': str(len(visible_temporary_paths))}
        if erased_visible:
            payload['erased_count'] = str(len(erased_visible))
            payload['erased_paths'] = ' | '.join(erased_visible)
        graph.add_diagnostic(
            Diagnostic(
                level='info',
                code='temporary_outputs_rendered',
                message=f'Rendered {len(visible_temporary_paths)} temporary outputs because display.show_temporary_outputs=true',
                payload=payload,
            )
        )

    for script, erased in sorted(script_erases.items()):
        for p in sorted(erased):
            graph.add_diagnostic(
                Diagnostic(
                    level='info',
                    code='erased_artifact',
                    message=f'Artifact erased inside script: {p}',
                    payload={'script': script, 'path': p},
                )
            )

    _add_version_family_diagnostics(graph, project_root, parser_config.version_families.mode)
    graph.excluded_paths.extend(sorted({path for path in do_files if is_excluded(path, exclusions)}))
    return graph


def write_edge_csv(graph: GraphModel, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open('w', newline='', encoding='utf-8') as handle:
        writer = csv.DictWriter(handle, fieldnames=['source', 'target', 'command', 'kind'])
        writer.writeheader()
        for edge in graph.edges:
            writer.writerow({'source': edge.source, 'target': edge.target, 'command': edge.operation, 'kind': edge.kind})
