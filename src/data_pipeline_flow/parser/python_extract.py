from __future__ import annotations

import re
from pathlib import Path

from data_pipeline_flow.config.schema import ExclusionConfig, NormalizationConfig, ParserConfig
from data_pipeline_flow.model.normalize import normalize_token, to_project_relative
from data_pipeline_flow.rules.exclusions import is_excluded
from data_pipeline_flow.parser.stata_extract import (
    Diagnostic,
    ParsedEvent,
    ScriptParseResult,
    _excluded_reference,
)

# ---------------------------------------------------------------------------
# Patterns: comment stripping
# ---------------------------------------------------------------------------
_COMMENT_RE = re.compile(r'#.*$')

# ---------------------------------------------------------------------------
# Patterns: variable assignment  VAR = "value"  or  VAR = 'value'
# ---------------------------------------------------------------------------
_VAR_ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(?:"([^"\\]*)"|\'([^\'\\]*)\')\s*$')

# ---------------------------------------------------------------------------
# Patterns: import alias tracking
#   import pandas as pd          -> lib_aliases['pd'] = 'pandas'
#   from pandas import read_csv  -> direct_imports.add(('pandas', 'read_csv'))
#   from pandas import read_csv as rc -> direct_imports.add(('pandas', 'read_csv')), alias_fns['rc'] = ('pandas', 'read_csv')
# ---------------------------------------------------------------------------
_IMPORT_AS_RE = re.compile(r'^\s*import\s+([\w.]+)\s+as\s+(\w+)')
_IMPORT_RE = re.compile(r'^\s*import\s+([\w.]+)')
_FROM_IMPORT_RE = re.compile(r'^\s*from\s+([\w.]+)\s+import\s+(.+)')

# ---------------------------------------------------------------------------
# Patterns: local module imports (for script-to-script edges)
# ---------------------------------------------------------------------------
_LOCAL_MOD_RE = re.compile(r'^\s*(?:import\s+([\w.]+)|from\s+([\w.]+)\s+import)')

# ---------------------------------------------------------------------------
# Patterns: subprocess script calls
#   subprocess.run(['python', 'script.py', ...])
#   subprocess.call(['python', 'script.py'])
#   subprocess.Popen(['python', 'script.py'])
#   runpy.run_path('script.py')
# ---------------------------------------------------------------------------
_SUBPROCESS_RE = re.compile(
    r'\bsubprocess\.(?:run|call|Popen)\s*\(\s*\[([^\]]+)\]'
)
_RUNPY_RE = re.compile(r'\brunpy\.run_path\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')')

# ---------------------------------------------------------------------------
# Patterns: pathlib.Path("literal") / "literal"  (all-literal case)
# ---------------------------------------------------------------------------
_PATH_DIV_RE = re.compile(
    r'\bPath\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')\s*\)\s*/\s*(?:"([^"]+)"|\'([^\']+)\')'
)

# ---------------------------------------------------------------------------
# Patterns: os.path.join("a", "b", ...)
# ---------------------------------------------------------------------------
_OSPATH_JOIN_RE = re.compile(r'\bos\.path\.join\s*\(([^)]+)\)')

# ---------------------------------------------------------------------------
# Quoted string anywhere (single or double)
# ---------------------------------------------------------------------------
_QUOTED_RE = re.compile(r'(?:"([^"\\]+)"|\'([^\'\\]+)\')')

# ---------------------------------------------------------------------------
# External reference filter
# ---------------------------------------------------------------------------
_EXTERNAL_PREFIXES = ('http://', 'https://', 'ftp://', 's3://', 'gs://')

# ---------------------------------------------------------------------------
# F-string resolution patterns
#   f"{VAR}/rest"  ->  "resolved_value/rest"
# ---------------------------------------------------------------------------
_FSTRING_DOUBLE_RE = re.compile(r'\bf"(\{(\w+)\}[^"]*?)"')
_FSTRING_SINGLE_RE = re.compile(r"\bf'(\{(\w+)\}[^']*?)'")


# ---------------------------------------------------------------------------
# READ patterns: (command_label, regex)
# Each regex must capture the path in group 1.
# ---------------------------------------------------------------------------

def _make_read_patterns(prefixes: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """Build read patterns for the given function prefixes (e.g. ['pd', 'pandas'])."""
    patterns: list[tuple[str, re.Pattern[str]]] = []
    read_fns = [
        ('read_csv', 'read_csv'),
        ('read_excel', 'read_excel'),
        ('read_parquet', 'read_parquet'),
        ('read_stata', 'read_stata'),
        ('read_json', 'read_json'),
        ('read_feather', 'read_feather'),
        ('read_table', 'read_table'),
        ('read_hdf', 'read_hdf'),
        ('read_pickle', 'read_pickle'),
        ('read_orc', 'read_orc'),
    ]
    for fn_name, cmd in read_fns:
        for prefix in prefixes:
            pat = re.compile(
                rf'\b{re.escape(prefix)}\.{re.escape(fn_name)}\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')',
                re.I,
            )
            patterns.append((cmd, pat))
    return patterns


def _make_np_read_patterns(prefixes: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for prefix in prefixes:
        for fn in ('load', 'loadtxt', 'genfromtxt'):
            patterns.append((
                f'np_{fn}',
                re.compile(rf'\b{re.escape(prefix)}\.{re.escape(fn)}\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I),
            ))
    return patterns


def _make_gpd_read_patterns(prefixes: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """Build read patterns for geopandas (gpd.read_file). Skips read_postgis (DB)."""
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for prefix in prefixes:
        patterns.append((
            'gpd_read_file',
            re.compile(rf'\b{re.escape(prefix)}\.read_file\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I),
        ))
    return patterns


# Fixed patterns that don't depend on aliases
_FIXED_READ_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ('open_read',     re.compile(r'\bopen\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')\s*(?:,\s*(?:"r[bt]?"|\'r[bt]?\'))?', re.I)),
    ('pickle_load',   re.compile(r'\bpickle\.load\s*\(\s*open\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('json_load',     re.compile(r'\bjson\.load\s*\(\s*open\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('yaml_safe_load',re.compile(r'\byaml\.(?:safe_load|load)\s*\(\s*open\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('joblib_load',   re.compile(r'\bjoblib\.load\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
]

# Default pandas/numpy alias patterns (used when no custom alias detected)
_DEFAULT_PD_READ = _make_read_patterns(['pd', 'pandas'])
_DEFAULT_NP_READ = _make_np_read_patterns(['np', 'numpy'])

# ---------------------------------------------------------------------------
# WRITE patterns
# ---------------------------------------------------------------------------

def _make_write_patterns(prefixes: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    patterns: list[tuple[str, re.Pattern[str]]] = []
    write_fns = [
        ('to_csv', 'to_csv'),
        ('to_excel', 'to_excel'),
        ('to_parquet', 'to_parquet'),
        ('to_stata', 'to_stata'),
        ('to_json', 'to_json'),
        ('to_feather', 'to_feather'),
        ('to_hdf', 'to_hdf'),
        ('to_pickle', 'to_pickle'),
        ('to_orc', 'to_orc'),
        ('to_file', 'to_file'),
    ]
    for fn_name, cmd in write_fns:
        # .to_csv("path") — method call, may have any object before the dot
        patterns.append((
            cmd,
            re.compile(rf'\.{re.escape(fn_name)}\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I),
        ))
    return patterns


def _make_plt_write_patterns(prefixes: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    patterns = []
    for prefix in prefixes:
        patterns.append((
            'savefig',
            re.compile(rf'\b{re.escape(prefix)}\.savefig\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I),
        ))
    return patterns


def _make_np_write_patterns(prefixes: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    patterns = []
    for prefix in prefixes:
        for fn in ('save', 'savetxt', 'savez', 'savez_compressed'):
            patterns.append((
                f'np_{fn}',
                re.compile(rf'\b{re.escape(prefix)}\.{re.escape(fn)}\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I),
            ))
    return patterns


_FIXED_WRITE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # .savefig("path") — method call (e.g. fig.savefig)
    ('savefig',       re.compile(r'\.savefig\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # open("path", "w"/"wb"/"a"/"ab")
    ('open_write',    re.compile(r'\bopen\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')\s*,\s*(?:"[wa][bt]?"|\'[wa][bt]?\')', re.I)),
    # pickle.dump(obj, open("path", "wb"))
    ('pickle_dump',   re.compile(r'\bpickle\.dump\s*\([^,]+,\s*open\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # json.dump(obj, open("path", "w"))
    ('json_dump',     re.compile(r'\bjson\.dump\s*\([^,]+,\s*open\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # joblib.dump(obj, "path")
    ('joblib_dump',   re.compile(r'\bjoblib\.dump\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # .save("path") — method call (folium, networkx, etc.)
    ('save_method',   re.compile(r'\.save\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
]

_DEFAULT_WRITE_PATTERNS = _make_write_patterns([])  # method patterns don't need a prefix
_DEFAULT_PLT_WRITE = _make_plt_write_patterns(['plt', 'matplotlib.pyplot'])
_DEFAULT_NP_WRITE = _make_np_write_patterns(['np', 'numpy'])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _strip_comment(line: str) -> str:
    """Remove inline # comments, preserving the line for number tracking."""
    # Don't strip inside strings — simple heuristic: find # not inside quotes
    in_single = False
    in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == '#' and not in_single and not in_double:
            return line[:i]
    return line


def _is_external(path: str) -> bool:
    return any(path.startswith(p) for p in _EXTERNAL_PREFIXES)


def _extract_quoted(text: str) -> str | None:
    """Return the first quoted string value found in text."""
    m = _QUOTED_RE.search(text)
    if m:
        return m.group(1) or m.group(2)
    return None


def _expand_var(path_expr: str, vars_map: dict[str, str]) -> str:
    """Expand simple variable references: replace known var names with their values."""
    stripped = path_expr.strip()
    return vars_map.get(stripped, stripped)


def _resolve_path_arg(raw: str, vars_map: dict[str, str]) -> str | None:
    """
    Try to resolve a function argument to a concrete path string.
    raw may be a quoted literal or a variable name.
    """
    stripped = raw.strip()
    # Already a quoted literal captured by regex group
    if stripped:
        return vars_map.get(stripped, None) if stripped in vars_map else stripped
    return None


def _try_match(pattern: re.Pattern[str], line: str, vars_map: dict[str, str]) -> str | None:
    """
    Try to match pattern against line.
    Groups 1 and 2 are alternative quoted captures (double / single quote).
    Returns resolved path or None.
    """
    m = pattern.search(line)
    if not m:
        return None
    raw = m.group(1) if m.group(1) is not None else m.group(2)
    if raw is None:
        return None
    return raw


def _resolve_ospath_join(text: str, vars_map: dict[str, str]) -> str | None:
    """Resolve os.path.join(...) if all args are literals or known vars."""
    m = _OSPATH_JOIN_RE.search(text)
    if not m:
        return None
    args_text = m.group(1)
    parts = []
    for piece in args_text.split(','):
        piece = piece.strip()
        quoted = _extract_quoted(piece)
        if quoted is not None:
            parts.append(quoted)
        elif piece in vars_map:
            parts.append(vars_map[piece])
        else:
            return None  # unresolvable
    return '/'.join(parts) if parts else None


def _resolve_path_div(text: str, vars_map: dict[str, str]) -> list[str]:
    """Resolve Path("a") / "b" / "c" all-literal chains."""
    results = []
    for m in _PATH_DIV_RE.finditer(text):
        a = m.group(1) or m.group(2)
        b = m.group(3) or m.group(4)
        if a and b:
            results.append(f'{a}/{b}')
    return results


def _module_to_path(module: str) -> str:
    """Convert a Python module name to a relative file path."""
    return module.replace('.', '/') + '.py'


def _collect_aliases(lines: list[str]) -> tuple[dict[str, str], set[str]]:
    """
    Pre-scan: collect import alias info.
    Returns:
        lib_aliases: {alias -> library_name}  e.g. {'pd': 'pandas'}
        direct_fn_names: set of function names directly imported (unqualified usage)
    """
    lib_aliases: dict[str, str] = {}
    direct_fn_names: set[str] = set()
    for line in lines:
        clean = _strip_comment(line)
        # import lib as alias
        m = _IMPORT_AS_RE.match(clean)
        if m:
            lib_aliases[m.group(2)] = m.group(1)
            continue
        # from lib import name [as alias], name2 [as alias2], ...
        m = _FROM_IMPORT_RE.match(clean)
        if m:
            _lib = m.group(1)
            names_part = m.group(2)
            for item in names_part.split(','):
                item = item.strip()
                if ' as ' in item:
                    _orig, _alias = item.split(' as ', 1)
                    direct_fn_names.add(_orig.strip())
                    direct_fn_names.add(_alias.strip())
                else:
                    direct_fn_names.add(item)
    return lib_aliases, direct_fn_names


def _build_dynamic_read_patterns(
    lib_aliases: dict[str, str],
    direct_fn_names: set[str],
) -> list[tuple[str, re.Pattern[str]]]:
    """Build additional read patterns based on detected import aliases."""
    extra: list[tuple[str, re.Pattern[str]]] = []

    # For each alias that maps to pandas/numpy/etc., add prefixed patterns
    pd_aliases = [alias for alias, lib in lib_aliases.items() if 'pandas' in lib]
    np_aliases = [alias for alias, lib in lib_aliases.items() if 'numpy' in lib]
    plt_aliases = [alias for alias, lib in lib_aliases.items() if 'matplotlib' in lib or 'pyplot' in lib]
    gpd_aliases = [alias for alias, lib in lib_aliases.items() if 'geopandas' in lib]

    if pd_aliases:
        extra.extend(_make_read_patterns(pd_aliases))
    if np_aliases:
        extra.extend(_make_np_read_patterns(np_aliases))
    if gpd_aliases:
        extra.extend(_make_gpd_read_patterns(gpd_aliases))
    else:
        # Always include default geopandas prefixes
        extra.extend(_make_gpd_read_patterns(['gpd', 'geopandas']))

    # For directly imported function names (from pandas import read_csv)
    direct_read_fns = {
        'read_csv', 'read_excel', 'read_parquet', 'read_stata', 'read_json',
        'read_feather', 'read_table', 'read_hdf', 'read_pickle', 'read_orc',
    }
    for fn in direct_fn_names & direct_read_fns:
        extra.append((
            fn,
            re.compile(rf'\b{re.escape(fn)}\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I),
        ))

    return extra


def _build_dynamic_write_patterns(
    lib_aliases: dict[str, str],
    direct_fn_names: set[str],
) -> list[tuple[str, re.Pattern[str]]]:
    extra: list[tuple[str, re.Pattern[str]]] = []
    np_aliases = [alias for alias, lib in lib_aliases.items() if 'numpy' in lib]
    plt_aliases = [alias for alias, lib in lib_aliases.items() if 'matplotlib' in lib or 'pyplot' in lib]
    if np_aliases:
        extra.extend(_make_np_write_patterns(np_aliases))
    if plt_aliases:
        extra.extend(_make_plt_write_patterns(plt_aliases))
    return extra


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_python_file(
    project_root: Path,
    py_file: Path,
    exclusions: ExclusionConfig,
    normalization: NormalizationConfig,
    parser_config: ParserConfig,
) -> ScriptParseResult:
    try:
        text = py_file.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ScriptParseResult(events=[], child_scripts=[], global_warnings=[])

    raw_lines = text.splitlines()
    rel_script, _ = to_project_relative(project_root, py_file, normalization)
    rel_script = normalize_token(rel_script)

    # --- Pre-pass 1: collect variable assignments ---
    vars_map: dict[str, str] = {}
    for line in raw_lines:
        clean = _strip_comment(line)
        m = _VAR_ASSIGN_RE.match(clean)
        if m:
            val = m.group(2) if m.group(2) is not None else m.group(3)
            vars_map[m.group(1)] = val

    # --- Pre-pass 2: collect import aliases ---
    lib_aliases, direct_fn_names = _collect_aliases(raw_lines)

    # --- Build combined pattern lists ---
    read_patterns = (
        _DEFAULT_PD_READ
        + _DEFAULT_NP_READ
        + _FIXED_READ_PATTERNS
        + _build_dynamic_read_patterns(lib_aliases, direct_fn_names)
    )
    write_patterns = (
        _DEFAULT_WRITE_PATTERNS
        + _DEFAULT_PLT_WRITE
        + _DEFAULT_NP_WRITE
        + _FIXED_WRITE_PATTERNS
        + _build_dynamic_write_patterns(lib_aliases, direct_fn_names)
    )

    events: list[ParsedEvent] = []
    child_scripts: list[str] = []
    global_warnings: list[Diagnostic] = []
    excluded_references: list[Diagnostic] = []

    seen_paths: set[tuple[str, str]] = set()  # (command, normalized_path) dedup

    def _add_event(line_no: int, command: str, raw_path: str, is_write: bool) -> None:
        if _is_external(raw_path):
            global_warnings.append(Diagnostic(
                level='info',
                code='external_reference',
                message=f'External reference skipped in {rel_script}:{line_no}: {raw_path}',
                payload={'script': rel_script, 'path': raw_path},
            ))
            return
        resolved_path = raw_path
        if '..' in raw_path and not Path(raw_path).is_absolute():
            resolved_path = str((py_file.parent / raw_path).resolve())
        norm, was_abs = to_project_relative(project_root, Path(resolved_path), normalization)
        norm = normalize_token(norm)
        if is_excluded(norm, exclusions):
            excluded_references.append(_excluded_reference(rel_script, line_no, command, norm))
            return
        key = (command, norm)
        if key in seen_paths:
            return
        seen_paths.add(key)
        events.append(ParsedEvent(
            script=rel_script,
            line=line_no,
            command=command,
            raw_path=raw_path,
            normalized_paths=[norm],
            was_absolute=was_abs,
        ))

    def _add_child(raw_path: str) -> None:
        norm, _ = to_project_relative(project_root, Path(raw_path), normalization)
        norm = normalize_token(norm)
        if norm not in child_scripts:
            child_scripts.append(norm)

    # --- Main line loop ---
    for line_no, raw_line in enumerate(raw_lines, start=1):
        line = _strip_comment(raw_line)

        # --- Script calls: local imports ---
        m_local = _LOCAL_MOD_RE.match(line)
        if m_local:
            module = m_local.group(1) or m_local.group(2)
            if module:
                candidate_path = _module_to_path(module)
                # Check relative to project root
                for base in (project_root, py_file.parent):
                    candidate = base / candidate_path
                    if candidate.exists():
                        _add_child(str(candidate.relative_to(project_root)).replace('\\', '/'))
                        break

        # --- Script calls: subprocess ---
        m_sub = _SUBPROCESS_RE.search(line)
        if m_sub:
            args_text = m_sub.group(1)
            # Extract all quoted strings from the list
            py_args = [
                (m.group(1) or m.group(2))
                for m in _QUOTED_RE.finditer(args_text)
            ]
            for arg in py_args:
                if arg and arg.endswith('.py'):
                    candidate = project_root / arg
                    if candidate.exists():
                        _add_child(arg)

        m_runpy = _RUNPY_RE.search(line)
        if m_runpy:
            raw = m_runpy.group(1) or m_runpy.group(2)
            if raw:
                _add_event(line_no, 'runpy', raw, is_write=False)

        # --- Resolve simple f-strings BEFORE variable expansion ---
        # Must run first: variable expansion would corrupt f"{VAR}/..." before we can resolve it.
        def _resolve_fstring_double(m: re.Match) -> str:
            inner, var = m.group(1), m.group(2)
            if var in vars_map:
                return '"' + inner.replace('{' + var + '}', vars_map[var]) + '"'
            return m.group(0)

        def _resolve_fstring_single(m: re.Match) -> str:
            inner, var = m.group(1), m.group(2)
            if var in vars_map:
                return '"' + inner.replace('{' + var + '}', vars_map[var]) + '"'
            return m.group(0)

        line = _FSTRING_DOUBLE_RE.sub(_resolve_fstring_double, line)
        line = _FSTRING_SINGLE_RE.sub(_resolve_fstring_single, line)

        # --- Expand bare variable names to quoted values for pattern matching ---
        for _var, _val in vars_map.items():
            line = re.sub(rf'\b{re.escape(_var)}\b', f'"{_val}"', line)

        # --- Path helper: os.path.join ---
        joined = _resolve_ospath_join(line, vars_map)
        if joined:
            # Replace in line for subsequent pattern matching (best-effort)
            line = line.replace(
                _OSPATH_JOIN_RE.search(line).group(0),  # type: ignore[union-attr]
                f'"{joined}"',
                1,
            )

        # --- Path helper: Path("a") / "b" ---
        for path_div_result in _resolve_path_div(line, vars_map):
            # We can't know read vs write from the Path() expression alone;
            # these typically appear as arguments to read/write functions,
            # so they'll be picked up by subsequent patterns below.
            # Replace the Path(...) / "..." expression with its resolved string.
            pass  # handled by substituting in subsequent patterns below

        # --- Read patterns ---
        for command, pattern in read_patterns:
            raw = _try_match(pattern, line, vars_map)
            if raw is not None:
                # Also try variable expansion
                expanded = vars_map.get(raw, raw)
                _add_event(line_no, command, expanded, is_write=False)
                break  # one read per line (first match)

        # --- Write patterns ---
        for command, pattern in write_patterns:
            raw = _try_match(pattern, line, vars_map)
            if raw is not None:
                expanded = vars_map.get(raw, raw)
                _add_event(line_no, command, expanded, is_write=True)
                break  # one write per line (first match)

    return ScriptParseResult(
        events=events,
        child_scripts=child_scripts,
        global_warnings=global_warnings,
        excluded_references=excluded_references,
    )
