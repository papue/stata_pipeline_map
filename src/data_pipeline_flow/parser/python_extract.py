from __future__ import annotations

import re
from pathlib import Path

from data_pipeline_flow.config.schema import ExclusionConfig, NormalizationConfig, ParserConfig
from data_pipeline_flow.model.normalize import _is_absolute_like, normalize_token, to_project_relative
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
# Also matches raw strings:  VAR = r"C:\path\to\dir"  or  b"..."
# ---------------------------------------------------------------------------
_VAR_ASSIGN_RE = re.compile(r'^\s*(\w+)\s*=\s*(?:[rRbBuU]?"([^"]*)"|[rRbBuU]?\'([^\']*)\')\s*$')

# ---------------------------------------------------------------------------
# Pattern: VAR = Path("literal")  (pathlib.Path wrapping a literal string)
# ---------------------------------------------------------------------------
_VAR_PATH_ASSIGN_RE = re.compile(
    r'^\s*(\w+)\s*=\s*(?:pathlib\.)?Path\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')\s*\)\s*$'
)

# ---------------------------------------------------------------------------
# Pattern: VAR = Path(other_var)  (pathlib.Path wrapping a variable)
# Resolved in sub-pass 1a when other_var is already in vars_map.
# ---------------------------------------------------------------------------
_VAR_PATH_VAR_ASSIGN_RE = re.compile(
    r'^\s*(\w+)\s*=\s*(?:pathlib\.)?Path\s*\(\s*(\w+)\s*\)\s*$'
)

# ---------------------------------------------------------------------------
# Pattern: VAR = os.path.join(...)  assignment
# ---------------------------------------------------------------------------
_VAR_OSPATH_JOIN_RE = re.compile(r'^\s*(\w+)\s*=\s*os\.path\.join\s*\(([^)]+)\)')

# ---------------------------------------------------------------------------
# Pattern: VAR = "{}/...".format(other_var)  or  VAR = "%s/..." % other_var
# ---------------------------------------------------------------------------
_VAR_FORMAT_METHOD_RE = re.compile(
    r'^\s*(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')\.format\s*\((\w+)\)'
)
_VAR_PERCENT_FORMAT_RE = re.compile(
    r'^\s*(\w+)\s*=\s*(?:"([^"]*)"|\'([^\']*)\')(?:\s*%\s*)(\w+)'
)

# ---------------------------------------------------------------------------
# Pattern: VAR = other_var + "suffix"  or  VAR = "prefix" + other_var
# ---------------------------------------------------------------------------
_VAR_CONCAT_RE = re.compile(
    r'^\s*(\w+)\s*=\s*(\w+)\s*\+\s*(?:"([^"]*)"|\'([^\']*)\')$'
)

# ---------------------------------------------------------------------------
# Pattern: VAR = token + token [+ token ...]   (general chained + concat)
# Each token is either a bare identifier (variable) or a quoted string literal.
# Captures: group(1)=var_name, group(2)=rest-of-RHS (everything after the '=')
# ---------------------------------------------------------------------------
_VAR_CONCAT_CHAIN_RE = re.compile(
    r'^\s*(\w+)\s*=\s*((?:(?:\w+|(?:[rRbBuU]?"[^"]*")|(?:[rRbBuU]?\'[^\']*\'))\s*\+\s*)*'
    r'(?:\w+|(?:[rRbBuU]?"[^"]*")|(?:[rRbBuU]?\'[^\']*\')))\s*$'
)

# ---------------------------------------------------------------------------
# Pattern: f-string with a known file extension (lower priority, produces
# a placeholder node so the edge is at least visible in the graph).
# Matches: f"...{expr}....<ext>"  where ext is a data file extension.
# ---------------------------------------------------------------------------
_FSTRING_WITH_EXT_RE = re.compile(
    r'\bf(?:"[^"]*\{[^}]+\}[^"]*\.(parquet|csv|pkl|pickle|feather|json|xlsx|dta|npy|npz|hdf|h5|orc|pdf|png|svg|eps)"'
    r"|'[^']*\{[^}]+\}[^']*\.(parquet|csv|pkl|pickle|feather|json|xlsx|dta|npy|npz|hdf|h5|orc|pdf|png|svg|eps)')",
    re.I,
)

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
# Quoted string anywhere (single or double); also raw/byte prefixed strings
# ---------------------------------------------------------------------------
_QUOTED_RE = re.compile(r'(?:[rRbBuU]?"([^"\\]+)"|[rRbBuU]?\'([^\'\\]+)\')')

# ---------------------------------------------------------------------------
# Pre-processor: strip r/b/u/R/B prefix from string literals so all
# subsequent patterns can match unadorned "..." and '...' strings.
# ---------------------------------------------------------------------------
_RAW_STR_PREFIX_RE = re.compile(r'\b([rRbBuU])((?:"[^"]*"|\'[^\']*\'))')

# ---------------------------------------------------------------------------
# External reference filter
# ---------------------------------------------------------------------------
_EXTERNAL_PREFIXES = ('http://', 'https://', 'ftp://', 's3://', 'gs://')

# ---------------------------------------------------------------------------
# Absolute path base detection
# A "real" absolute base has multiple path components (not a bare filename or
# a single-segment suffix like "/file.csv").  This prevents values like
# "/results_final.csv" from being treated as absolute path variables.
# ---------------------------------------------------------------------------
_WINDOWS_ABS_RE = re.compile(r'^[A-Za-z]:[/\\]')


def _is_absolute_base(val: str) -> bool:
    """Return True only when *val* looks like an absolute directory base.

    Unlike ``_is_absolute_like``, this excludes bare ``/filename.ext`` strings
    so that path-suffix variables (``suffix = "/file.csv"``) are NOT added to
    ``abs_vars`` and can participate in normal string concatenation.
    """
    # Windows drive-letter paths: C:\ or C:/
    if _WINDOWS_ABS_RE.match(val):
        return True
    # UNC paths: \\server\share
    if val.startswith('\\\\'):
        return True
    # Unix absolute: must have at least one segment beyond the leading /
    # e.g. "/home/user" yes, "/file.csv" no
    if val.startswith('/'):
        rest = val.lstrip('/')
        # If the remainder has a directory separator it's a multi-segment abs path
        if '/' in rest or '\\' in rest:
            return True
        # Single segment starting with /: treat as a suffix, not an abs base
        return False
    return False

# ---------------------------------------------------------------------------
# __file__-based variable resolution patterns
# ---------------------------------------------------------------------------
# VAR = os.path.dirname(os.path.abspath(__file__))  or  os.path.dirname(__file__)
_DIRNAME_FILE_RE = re.compile(
    r'^\s*(\w+)\s*=\s*os\.path\.dirname\s*\(\s*(?:os\.path\.abspath\s*\(\s*)?__file__\s*\)?',
)
# VAR = Path(__file__)[.resolve()][.parent]* [/ "literal"]*
# Handles: Path(__file__).parent, Path(__file__).resolve().parent.parent / "data", etc.
_PATH_FILE_RE = re.compile(
    r'^\s*(\w+)\s*=\s*(?:pathlib\.)?Path\s*\(\s*__file__\s*\)'
    r'((?:\.resolve\(\)|\.parent)*)'
    r'((?:\s*/\s*(?:"[^"]+"|\'[^\']+\'))*)\s*$'
)
# VAR = other_pathlib_var[.parent]* [/ "literal"]*
_PATHLIB_CHAIN_RE = re.compile(
    r'^\s*(\w+)\s*=\s*(\w+)((?:\.parent|\.resolve\(\))*)'
    r'((?:\s*/\s*(?:"[^"]+"|\'[^\']+\'))*)\s*$'
)
# Inline Path("a") / "b" [/ "c"]* (after variable expansion) — one or more divisions
_PATH_DIV_INLINE_RE = re.compile(
    r'\bPath\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')\s*\)\s*(?:/\s*(?:"[^"]+"|\'[^\']+\')\s*)+'
)
# Inline Path("val") with NO following / — transparent unwrap to "val"
# (must not match when followed by / since _PATH_DIV_INLINE_RE handles that)
_PATH_WRAP_INLINE_RE = re.compile(
    r'\bPath\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')\s*\)(?!\s*/)'
)
# Inline "a" + "b"  string concatenation (after variable expansion)
_STR_CONCAT_INLINE_RE = re.compile(r'"([^"]*?)"\s*\+\s*"([^"]*?)"')
# Inline "a" / "b" [/ "c"]*  path division (after variable expansion replaces pathlib vars)
# This handles cases like: pd.read_csv("data" / "input.csv") after expansion
_STR_DIV_INLINE_RE = re.compile(r'"([^"]*?)"\s*(?:/\s*"[^"]*?"\s*)+')

# ---------------------------------------------------------------------------
# Pattern: os.listdir(VAR_OR_LITERAL)  — directory-scan read
# ---------------------------------------------------------------------------
_LISTDIR_RE = re.compile(r'\bos\.listdir\s*\(([^)]+)\)')

# Pattern: os.walk(VAR_OR_LITERAL)  — recursive directory-scan read
_OSWALK_RE = re.compile(r'\bos\.walk\s*\(([^)]+)\)')

# Pattern: detect .endswith(".ext") suffix filter on nearby lines
_ENDSWITH_RE = re.compile(r'\.endswith\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')\s*\)')

# Pattern: with open(VAR, "rb") — two-line binary read
_WITH_OPEN_VAR_RB_RE = re.compile(
    r'\bwith\s+open\s*\(\s*(\w+)\s*,\s*(?:[rRbBuU]?"r[bt]?"|[rRbBuU]?\'r[bt]?\')',
)

# ---------------------------------------------------------------------------
# Kwarg path heuristic — names of keyword arguments that commonly carry a
# file-path value.  When a function call passes one of these kwargs with a
# resolved string value we emit a write edge from the call site.
# ---------------------------------------------------------------------------
_PATH_KWARG_NAMES: frozenset[str] = frozenset({
    'filename', 'path', 'output', 'output_path', 'save_path',
    'filepath', 'file', 'fname',
})
# Matches:  keyword="literal"  or  keyword='literal'  or  keyword=variable
_KWARG_PATH_RE = re.compile(
    r'\b(' + '|'.join(_PATH_KWARG_NAMES) + r')\s*=\s*'
    r'(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\'|(\w+))'
)

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
                rf'\b{re.escape(prefix)}\.{re.escape(fn_name)}\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')',
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
                re.compile(rf'\b{re.escape(prefix)}\.{re.escape(fn)}\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I),
            ))
    return patterns


def _make_gpd_read_patterns(prefixes: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    """Build read patterns for geopandas (gpd.read_file). Skips read_postgis (DB)."""
    patterns: list[tuple[str, re.Pattern[str]]] = []
    for prefix in prefixes:
        patterns.append((
            'gpd_read_file',
            re.compile(rf'\b{re.escape(prefix)}\.read_file\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I),
        ))
    return patterns


# Fixed patterns that don't depend on aliases
_FIXED_READ_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # open("path") with no mode arg (defaults to "r") OR explicit read mode "r"/"rt"/"rb".
    # Modes "w"/"wb"/"a"/"ab" must NOT match (they are handled by open_write).
    # A negative lookahead after the path ensures that a write mode following a comma
    # prevents this pattern from firing.  The lookahead blocks ,<opt-ws>"w..."/"a..."
    # while still allowing no-mode (bare open("path")) and explicit read modes.
    ('open_read',     re.compile(r'\bopen\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')\s*(?!,\s*(?:[rRbBuU]?"[wa][bt]?"|[rRbBuU]?\'[wa][bt]?\'))', re.I)),
    ('pickle_load',   re.compile(r'\bpickle\.load\s*\(\s*open\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I)),
    ('json_load',     re.compile(r'\bjson\.load\s*\(\s*open\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I)),
    ('yaml_safe_load',re.compile(r'\byaml\.(?:safe_load|load)\s*\(\s*open\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I)),
    ('joblib_load',   re.compile(r'\bjoblib\.load\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I)),
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
            re.compile(rf'\.{re.escape(fn_name)}\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I),
        ))
    return patterns


def _make_plt_write_patterns(prefixes: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    patterns = []
    for prefix in prefixes:
        patterns.append((
            'savefig',
            re.compile(rf'\b{re.escape(prefix)}\.savefig\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I),
        ))
    return patterns


def _make_np_write_patterns(prefixes: list[str]) -> list[tuple[str, re.Pattern[str]]]:
    patterns = []
    for prefix in prefixes:
        for fn in ('save', 'savetxt', 'savez', 'savez_compressed'):
            patterns.append((
                f'np_{fn}',
                re.compile(rf'\b{re.escape(prefix)}\.{re.escape(fn)}\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I),
            ))
    return patterns


_FIXED_WRITE_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # .savefig("path") — method call (e.g. fig.savefig)
    ('savefig',       re.compile(r'\.savefig\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I)),
    # pickle.dump(obj, open("path", "wb")) — more specific than open_write
    ('pickle_dump',   re.compile(r'\bpickle\.dump\s*\([^,]+,\s*open\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I)),
    # json.dump(obj, open("path", "w")) — more specific than open_write
    ('json_dump',     re.compile(r'\bjson\.dump\s*\([^,]+,\s*open\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I)),
    # open("path", "w"/"wb"/"a"/"ab")
    ('open_write',    re.compile(r'\bopen\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')\s*,\s*(?:[rRbBuU]?"[wa][bt]?"|[rRbBuU]?\'[wa][bt]?\')', re.I)),
    # joblib.dump(obj, "path")
    ('joblib_dump',   re.compile(r'\bjoblib\.dump\s*\([^,]+,\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I)),
    # .save("path") — method call (folium, networkx, etc.)
    ('save_method',   re.compile(r'\.save\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I)),
    # pathlib .write_text() / .write_bytes() — after variable expansion the path
    # variable becomes a quoted string, so we match "path".write_text(
    ('write_text',    re.compile(r'(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')\.write_text\s*\(', re.I)),
    ('write_bytes',   re.compile(r'(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')\.write_bytes\s*\(', re.I)),
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


def _resolve_ospath_join(
    text: str,
    vars_map: dict[str, str],
    abs_vars: set[str] | None = None,
    partial_wildcard: bool = False,
) -> tuple[str | None, bool]:
    """Resolve os.path.join(...) if all args are literals or known vars.

    Returns ``(resolved_path, contained_absolute)`` where ``contained_absolute``
    is True when an absolute-path variable was encountered as one of the
    arguments.  In that case only the non-absolute literal suffix parts are
    joined so that a partial (flagged) edge can still be emitted.

    When *partial_wildcard* is True, unresolvable arguments are substituted
    with ``*`` instead of causing the whole join to fail.  This allows dynamic
    paths like ``os.path.join(KNOWN_BASE, loop_var, "file.pkl")`` to produce
    a useful placeholder node such as ``known_base/*/file.pkl``.
    """
    m = _OSPATH_JOIN_RE.search(text)
    if not m:
        return None, False
    args_text = m.group(1)
    parts: list[str] = []
    contained_absolute = False
    had_wildcard = False
    for piece in args_text.split(','):
        piece = piece.strip()
        # A compound expression like `name + ".pdf"` is NOT a pure quoted literal.
        # _extract_quoted would return only ".pdf" (the extension suffix), which
        # would produce a garbled node like "output/.pdf".  Detect compound pieces
        # (identifier + string) and treat them as unresolvable.
        _is_compound = bool(re.search(r'\b[A-Za-z_]\w*\s*\+', piece))
        quoted = None if _is_compound else _extract_quoted(piece)
        if quoted is not None:
            if _is_absolute_like(quoted):
                # Skip absolute base components — we keep only the literal suffix parts
                contained_absolute = True
            else:
                parts.append(quoted)
        elif piece in vars_map:
            val = vars_map[piece]
            if abs_vars is not None and piece in abs_vars:
                # Skip the absolute base — we keep only the literal suffix parts
                contained_absolute = True
            else:
                parts.append(val)
        else:
            if partial_wildcard:
                # Substitute unresolvable arg with wildcard segment
                parts.append('*')
                had_wildcard = True
            else:
                if contained_absolute:
                    # We already found an absolute prefix; remaining unknowns block resolution
                    return None, True
                return None, False  # unresolvable
    if not parts:
        return None, contained_absolute
    # Remove leading wildcard-only segments (keep at least the literal suffix parts)
    # so that os.path.join(unknown, "file.pkl") → "file.pkl" not "*/file.pkl".
    while parts and parts[0] == '*':
        parts = parts[1:]
        had_wildcard = True
    if not parts:
        return None, contained_absolute
    raw_joined = '/'.join(parts)
    # Normalize ".." segments so "analysis/../results" becomes "results"
    norm_parts: list[str] = []
    for seg in raw_joined.split('/'):
        if seg == '..':
            if norm_parts:
                norm_parts.pop()
        elif seg and seg != '.':
            norm_parts.append(seg)
    return '/'.join(norm_parts) if norm_parts else '.', contained_absolute


def _extract_fstring_placeholder(raw_fstring: str) -> str | None:
    """
    Given the content of an f-string that still contains ``{expr}`` placeholders,
    return a sanitised placeholder path like ``{dynamic}/result_*.pkl`` if the
    f-string ends with a recognised data-file extension.

    The heuristic replaces every ``{...}`` block with ``*`` so the placeholder
    looks like a glob pattern, making it obvious that the exact filename varies.
    """
    # Strip surrounding quotes and the leading f/F
    content = raw_fstring
    for prefix in ('f"', "f'", 'F"', "F'"):
        if content.startswith(prefix):
            content = content[len(prefix):]
            break
    if content.endswith('"') or content.endswith("'"):
        content = content[:-1]
    # Replace {expr} blocks with *
    placeholder = re.sub(r'\{[^}]+\}', '*', content)
    return placeholder


def _resolve_path_div(text: str, vars_map: dict[str, str]) -> list[str]:
    """Resolve Path("a") / "b" / "c" all-literal chains."""
    results = []
    for m in _PATH_DIV_RE.finditer(text):
        a = m.group(1) or m.group(2)
        b = m.group(3) or m.group(4)
        if a and b:
            results.append(f'{a}/{b}')
    return results


def _resolve_concat_chain(
    rhs: str,
    vars_map: dict[str, str],
    abs_vars: set[str],
) -> tuple[str | None, bool]:
    """Resolve a chain of ``+`` concatenations (e.g. ``a + b + "/file.csv"``).

    Each token is a bare identifier (variable) or a quoted string literal.
    Returns ``(resolved_string, contained_absolute)`` where
    ``contained_absolute`` is True when an absolute-path variable was part of
    the chain (so the caller can emit a ``force_abs`` edge instead of dropping
    the result entirely).

    Returns ``(None, False)`` if any token cannot be resolved.
    """
    # Tokenize: split on '+' and classify each piece
    _TOKEN_RE = re.compile(
        r'[rRbBuU]?"([^"]*)"|[rRbBuU]?\'([^\']*)\'|(\w+)'
    )
    tokens = rhs.split('+')
    parts: list[str] = []
    contained_absolute = False
    for tok in tokens:
        tok = tok.strip()
        m = _TOKEN_RE.fullmatch(tok)
        if not m:
            return None, False
        if m.group(1) is not None or m.group(2) is not None:
            # Quoted literal
            lit = m.group(1) if m.group(1) is not None else m.group(2)
            # Normalise Windows backslash separators
            parts.append(lit.replace('\\', '/'))
        else:
            # Bare identifier — look up in vars_map
            var = m.group(3)
            if var not in vars_map:
                return None, False
            if var in abs_vars:
                contained_absolute = True
                # Skip the absolute prefix — only keep non-absolute suffix parts
            else:
                parts.append(vars_map[var].replace('\\', '/'))
    if not parts:
        return None, contained_absolute
    joined = ''.join(parts)
    # Normalise path separators and redundant slashes
    joined = joined.replace('//', '/')
    return joined, contained_absolute


def _module_to_path(module: str) -> str:
    """Convert a Python module name to a relative file path."""
    return module.replace('.', '/') + '.py'


def extract_module_constants(py_file: Path) -> dict[str, str]:
    """Extract top-level ``NAME = "literal"`` (or ``Path("literal")``) string
    constants from *py_file*.

    This is a lightweight pre-scan used by multi_extract.py to build a
    cross-module constant map for ``from <module> import NAME`` resolution.
    Only simple string assignments are extracted; dynamic values are ignored.

    Returns a mapping of variable name → string value.
    """
    try:
        text = py_file.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return {}
    constants: dict[str, str] = {}
    for raw_line in text.splitlines():
        clean = _strip_comment(raw_line)
        # Plain string literal: NAME = "value" or NAME = 'value'
        m = _VAR_ASSIGN_RE.match(clean)
        if m:
            val = m.group(2) if m.group(2) is not None else m.group(3)
            constants[m.group(1)] = val
            continue
        # Path("literal") wrapping: NAME = Path("value")
        m2 = _VAR_PATH_ASSIGN_RE.match(clean)
        if m2:
            val = m2.group(2) if m2.group(2) is not None else m2.group(3)
            constants[m2.group(1)] = val
    return constants


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
            re.compile(rf'\b{re.escape(fn)}\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')', re.I),
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
    imported_constants: dict[str, str] | None = None,
) -> ScriptParseResult:
    try:
        text = py_file.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ScriptParseResult(events=[], child_scripts=[], global_warnings=[])

    raw_lines = text.splitlines()
    rel_script, _ = to_project_relative(project_root, py_file, normalization)
    rel_script = normalize_token(rel_script)

    # --- Pre-pass 0: join continuation lines (multi-line parenthesised expressions) ---
    # This allows os.path.join(...) and Path(...) expressions that span multiple
    # lines to be matched by single-line regexes.
    joined_lines: list[str] = []
    _pending = ''
    _open_parens = 0
    for raw_line in raw_lines:
        clean_cl = _strip_comment(raw_line)
        _open_parens += clean_cl.count('(') - clean_cl.count(')')
        if _open_parens > 0:
            # continuation — accumulate
            _pending += ' ' + clean_cl.strip()
        else:
            if _pending:
                joined_lines.append(_pending + ' ' + clean_cl.strip())
                _pending = ''
                _open_parens = 0
            else:
                joined_lines.append(raw_line)
    if _pending:
        joined_lines.append(_pending)

    # --- Pre-pass 0b: substitute known __file__-based and os.sep expressions ---
    # Replace os.path.dirname(os.path.abspath(__file__)) and similar compound
    # expressions with a placeholder variable name so that _resolve_ospath_join
    # and other patterns can match them as simple variable references.
    # We use the sentinel name __script_dir__ (unlikely to collide).
    # Matches both:
    #   os.path.dirname(__file__)
    #   os.path.dirname(os.path.abspath(__file__))
    # We need to match the complete expression including all closing parens.
    _OSPATH_DIRNAME_FILE_EXPR = re.compile(
        r'os\.path\.dirname\s*\(\s*os\.path\.abspath\s*\(\s*__file__\s*\)\s*\)'
        r'|os\.path\.dirname\s*\(\s*__file__\s*\)'
    )
    _OSSEP_RE = re.compile(r'\bos\.sep\b')
    _joined_lines_sub: list[str] = []
    for _jl in joined_lines:
        _jl = _OSPATH_DIRNAME_FILE_EXPR.sub('__script_dir__', _jl)
        _jl = _OSSEP_RE.sub('"/"', _jl)  # treat os.sep as "/" for path resolution
        _joined_lines_sub.append(_jl)
    joined_lines = _joined_lines_sub

    # --- Pre-pass 1: collect variable assignments ---
    # Two sub-passes so that joined-path vars can reference already-resolved vars.
    vars_map: dict[str, str] = {}
    abs_vars: set[str] = set()  # variable names whose values are absolute paths

    # Seed __file__ with the script's absolute path so os.path.dirname/__file__
    # and Path(__file__) expressions can be resolved.
    vars_map['__file__'] = str(py_file).replace('\\', '/')
    abs_vars.add('__file__')
    # os.sep is always treated as '/' for path resolution purposes
    # (paths are normalised to forward slashes throughout the tool).
    # We can't add 'os.sep' directly as a var name (contains a dot) so we
    # pre-substitute it in the joined_lines below.
    # __script_dir__ is our internal sentinel for os.path.dirname(os.path.abspath(__file__))
    # (substituted in joined_lines above).  It holds the project-relative folder.
    _script_dir_for_vars = str(py_file.parent.relative_to(project_root)).replace('\\', '/')
    if _script_dir_for_vars == '.':
        _script_dir_for_vars = ''
    vars_map['__script_dir__'] = _script_dir_for_vars if _script_dir_for_vars else '.'

    # Seed imported constants from other project modules (cross-script global propagation).
    # These are injected before sub-pass 1a so that f-string / variable-path resolution
    # in the importing script can use them.  Local assignments (sub-pass 1a and later)
    # will overwrite these if the same name is re-defined locally.
    if imported_constants:
        for _ic_name, _ic_val in imported_constants.items():
            vars_map[_ic_name] = _ic_val
            if _is_absolute_base(_ic_val):
                abs_vars.add(_ic_name)

    # Sub-pass 1a: plain string literals  VAR = "value"  or  VAR = r"value"
    _VAR_ASSIGN_SENTINEL_RE = re.compile(r'^\s*(\w+)\s*=\s*__script_dir__\s*$')
    for line in joined_lines:
        clean = _strip_comment(line)
        m = _VAR_ASSIGN_RE.match(clean)
        if m:
            val = m.group(2) if m.group(2) is not None else m.group(3)
            vars_map[m.group(1)] = val
            if _is_absolute_base(val):
                abs_vars.add(m.group(1))
        # VAR = Path("literal")
        m2 = _VAR_PATH_ASSIGN_RE.match(clean)
        if m2:
            val = m2.group(2) if m2.group(2) is not None else m2.group(3)
            vars_map[m2.group(1)] = val
        # VAR = __script_dir__  (after pre-pass substitution)
        m3 = _VAR_ASSIGN_SENTINEL_RE.match(clean)
        if m3:
            vars_map[m3.group(1)] = vars_map['__script_dir__']

    # Sub-pass 1a2: VAR = Path(other_var)  — transparent Path wrapping of a variable.
    # Runs after 1a so that other_var is already resolved in vars_map.
    # Repeat to handle chains like:  a = os.path.join(...); b = Path(a)
    for line in joined_lines:
        clean = _strip_comment(line)
        m_pv = _VAR_PATH_VAR_ASSIGN_RE.match(clean)
        if m_pv:
            var_name = m_pv.group(1)
            src_var = m_pv.group(2)
            if src_var in vars_map and var_name not in vars_map:
                vars_map[var_name] = vars_map[src_var]
                if src_var in abs_vars:
                    abs_vars.add(var_name)

    # Sub-pass 1b: VAR = os.path.join(...)  where components resolve from vars_map
    # Run on joined_lines so multi-line joins are captured.
    # Also handles VAR = os.path.join(...) + "suffix" (e.g. + "/" for trailing sep).
    # Also handles VAR = os.path.abspath(os.path.join(...)) — the abspath wrapper is
    # transparent for path-node-ID purposes because we normalise all paths anyway.
    _VAR_OSPATH_JOIN_PLUS_RE = re.compile(
        r'^\s*(\w+)\s*=\s*os\.path\.join\s*\(([^)]+)\)\s*\+\s*(?:"([^"]*)"|\'([^\']*)\')'
    )
    _VAR_OSPATH_ABSPATH_JOIN_RE = re.compile(
        r'^\s*(\w+)\s*=\s*os\.path\.abspath\s*\(\s*os\.path\.join\s*\('
    )
    for line in joined_lines:
        clean = _strip_comment(line)
        m_plus = _VAR_OSPATH_JOIN_PLUS_RE.match(clean)
        if m_plus:
            var_name = m_plus.group(1)
            jpath, _abs = _resolve_ospath_join(clean, vars_map, abs_vars)
            if jpath is not None:
                suffix = m_plus.group(3) if m_plus.group(3) is not None else m_plus.group(4)
                vars_map[var_name] = jpath + suffix
                if _abs:
                    abs_vars.add(var_name)
            continue
        # VAR = os.path.abspath(os.path.join(...)) — strip the abspath wrapper and
        # resolve the inner join exactly as the plain os.path.join case.
        m_abs = _VAR_OSPATH_ABSPATH_JOIN_RE.match(clean)
        if m_abs:
            var_name = m_abs.group(1)
            jpath, _abs = _resolve_ospath_join(clean, vars_map, abs_vars)
            if jpath is not None:
                vars_map[var_name] = jpath
                if _abs:
                    abs_vars.add(var_name)
            continue
        m = _VAR_OSPATH_JOIN_RE.match(clean)
        if m:
            var_name = m.group(1)
            jpath, _abs = _resolve_ospath_join(clean, vars_map, abs_vars)
            if jpath is not None:
                vars_map[var_name] = jpath
                if _abs:
                    abs_vars.add(var_name)
            else:
                # Full resolution failed — try partial wildcard so that
                # path = os.path.join(known_base, loop_var) → "known_base/*"
                # This allows downstream os.listdir(path) / open(join(path,"f")) to resolve.
                jpath_p, _abs_p = _resolve_ospath_join(clean, vars_map, abs_vars, partial_wildcard=True)
                if jpath_p is not None and '*' in jpath_p:
                    vars_map[var_name] = jpath_p
                    if _abs_p:
                        abs_vars.add(var_name)

    # Sub-pass 1c: VAR = "{}/...".format(other)  and  VAR = "%s/..." % other
    for line in joined_lines:
        clean = _strip_comment(line)
        m = _VAR_FORMAT_METHOD_RE.match(clean)
        if m:
            var_name = m.group(1)
            template = m.group(2) if m.group(2) is not None else m.group(3)
            arg_var = m.group(4)
            if arg_var in vars_map and arg_var not in abs_vars:
                resolved = template.replace('{}', vars_map[arg_var], 1)
                vars_map[var_name] = resolved
        m2 = _VAR_PERCENT_FORMAT_RE.match(clean)
        if m2:
            var_name = m2.group(1)
            template = m2.group(2) if m2.group(2) is not None else m2.group(3)
            arg_var = m2.group(4)
            if arg_var in vars_map and arg_var not in abs_vars:
                resolved = template.replace('%s', vars_map[arg_var], 1)
                vars_map[var_name] = resolved

    # Sub-pass 1d: VAR = token + token [+ token ...]
    # Handles: var + "suffix", "prefix" + var, var + var, and chained a+b+c.
    # When the chain contains an abs_var, we still store the non-absolute suffix
    # parts so a force_abs edge can be emitted at the call site.
    for line in joined_lines:
        clean = _strip_comment(line)
        m = _VAR_CONCAT_CHAIN_RE.match(clean)
        if not m:
            continue
        var_name = m.group(1)
        rhs = m.group(2)
        # Skip if RHS contains no '+' (plain assignment already handled in 1a)
        if '+' not in rhs:
            continue
        resolved, is_abs = _resolve_concat_chain(rhs, vars_map, abs_vars)
        if resolved is not None:
            vars_map[var_name] = resolved
            if is_abs:
                abs_vars.add(var_name)

    # Sub-pass 1e: resolve __file__-based path variables
    # Patterns handled:
    #   VAR = os.path.dirname(os.path.abspath(__file__))
    #   VAR = os.path.dirname(__file__)
    #   VAR = Path(__file__) / then .parent chains tracked via pathlib_vars
    # We represent script_dir as the project-relative folder of the script.
    _script_dir_rel = str(py_file.parent.relative_to(project_root)).replace('\\', '.')
    # Normalise to forward-slash relative path; '.' means project root
    _script_dir_rel = str(py_file.parent.relative_to(project_root)).replace('\\', '/')
    if _script_dir_rel == '.':
        _script_dir_rel = ''

    # Track Path objects (pathlib vars) — map varname -> Path object
    pathlib_vars: dict[str, Path] = {}

    for line in joined_lines:
        clean = _strip_comment(line)
        m = _DIRNAME_FILE_RE.match(clean)
        if m:
            var_name = m.group(1)
            vars_map[var_name] = _script_dir_rel if _script_dir_rel else '.'
        m2 = _PATH_FILE_RE.match(clean)
        if m2:
            var_name = m2.group(1)
            chain = m2.group(2)   # e.g. ".resolve().parent.parent"
            divs = m2.group(3)    # e.g. ' / "data"'
            current_path = py_file
            for part in re.findall(r'\.(parent|resolve\(\))', chain):
                if part == 'parent':
                    current_path = current_path.parent
            for div_lit in re.findall(r'(?:"([^"]+)"|\'([^\']+)\')', divs):
                lit = div_lit[0] or div_lit[1]
                current_path = current_path / lit
            pathlib_vars[var_name] = current_path

    # Resolve pathlib chains: VAR = other_pathlib_var[.parent]* [/ "literal"]*
    # Keep iterating until no new vars are resolved.
    changed = True
    max_iter = 10
    while changed and max_iter > 0:
        changed = False
        max_iter -= 1
        for line in joined_lines:
            clean = _strip_comment(line)
            m = _PATHLIB_CHAIN_RE.match(clean)
            if not m:
                continue
            var_name = m.group(1)
            base_var = m.group(2)
            chain = m.group(3)  # e.g. ".parent.parent"
            divs = m.group(4)   # e.g. ' / "data"'
            if base_var not in pathlib_vars:
                continue
            if var_name in pathlib_vars:
                continue  # already resolved
            current_path = pathlib_vars[base_var]
            # Apply .parent and .resolve() calls
            for part in re.findall(r'\.(parent|resolve\(\))', chain):
                if part == 'parent':
                    current_path = current_path.parent
                # .resolve() — we keep as-is (already absolute)
            # Apply / "literal" divisions
            for div_lit in re.findall(r'(?:"([^"]+)"|\'([^\']+)\')', divs):
                lit = div_lit[0] or div_lit[1]
                current_path = current_path / lit
            pathlib_vars[var_name] = current_path
            changed = True

    # For each resolved pathlib var, add it to vars_map as a relative path
    for var_name, p in pathlib_vars.items():
        if var_name == '__file__':
            continue
        try:
            rel = p.resolve().relative_to(project_root.resolve())
            vars_map[var_name] = str(rel).replace('\\', '/')
        except ValueError:
            # Not under project_root — store absolute for os.path.join usage
            vars_map[var_name] = str(p).replace('\\', '/')
            abs_vars.add(var_name)

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

    def _add_event(line_no: int, command: str, raw_path: str, is_write: bool, force_abs: bool = False) -> None:
        if _is_external(raw_path):
            global_warnings.append(Diagnostic(
                level='info',
                code='external_reference',
                message=f'External reference skipped in {rel_script}:{line_no}: {raw_path}',
                payload={'script': rel_script, 'path': raw_path},
            ))
            return
        # Guard: a raw_path that ends with "/" (e.g. "./" or "../data/") is a
        # directory-only prefix captured because the read pattern grabbed only the
        # first quoted literal before a runtime variable in the middle of a concat
        # expression (e.g. open("./" + VAR + ".json")).  Such fragments produce
        # spurious nodes like "." or "data"; drop them silently.
        if raw_path.endswith('/') or raw_path.endswith('\\'):
            return
        resolved_path = raw_path
        if '..' in raw_path and not Path(raw_path).is_absolute():
            resolved_path = str((py_file.parent / raw_path).resolve())
        norm, was_abs = to_project_relative(project_root, Path(resolved_path), normalization)
        norm = normalize_token(norm)
        # When force_abs=True the path came from stripping an absolute base in
        # os.path.join(abs_var, "suffix").  The remaining suffix may be just a
        # bare filename with no directory component.  If the file actually exists
        # somewhere inside the project tree, use that project-relative path so
        # the node ID matches the one produced by __file__-relative reads.
        if force_abs and '/' not in norm and norm not in {'.', ''}:
            matches = list(project_root.rglob(norm))
            if len(matches) == 1:
                try:
                    norm = normalize_token(str(matches[0].relative_to(project_root)).replace('\\', '/'))
                except ValueError:
                    pass  # outside project_root — keep bare filename
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
            was_absolute=was_abs or force_abs,
            is_write=is_write,
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
                    try:
                        exists = candidate.exists()
                    except OSError:
                        # Can happen on Windows when the candidate resolves to a
                        # UNC path (e.g. //server/share) that is not reachable.
                        exists = False
                    if exists:
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

        # --- Path helper: os.path.join (run BEFORE variable expansion) ---
        # Must run before variable expansion so that abs_vars detection works:
        # if BASE is an absolute-path variable, _resolve_ospath_join sees "BASE"
        # in the args and uses abs_vars to skip it, returning only the literal
        # suffix components so a partial (flagged) edge can still be emitted.
        joined, join_was_abs = _resolve_ospath_join(line, vars_map, abs_vars)
        if joined:
            # Replace os.path.join(...) expression with the resolved string so
            # subsequent read/write patterns can match it as a quoted literal.
            line = line.replace(
                _OSPATH_JOIN_RE.search(line).group(0),  # type: ignore[union-attr]
                f'"{joined}"',
                1,
            )
        else:
            # Full resolution failed — try partial-wildcard resolution so that
            # os.path.join(known_base, loop_var, "file.pkl") → "known_base/*/file.pkl"
            joined_partial, _ = _resolve_ospath_join(line, vars_map, abs_vars, partial_wildcard=True)
            if joined_partial and '*' in joined_partial:
                _m_join = _OSPATH_JOIN_RE.search(line)
                if _m_join:
                    line = line.replace(_m_join.group(0), f'"{joined_partial}"', 1)
        # Track whether the current line's join resolution involved an absolute var
        _join_force_abs = join_was_abs

        # --- Expand bare variable names to quoted values for pattern matching ---
        # Skip absolute-path variables: they are only useful inside os.path.join
        # (handled above) and expanding them would insert Windows paths with
        # backslashes that confuse _QUOTED_RE and other patterns.
        # However, we also expand abs_vars at read/write call sites (marked
        # force_abs so the diagnostic is emitted).
        _line_has_abs_var = False
        for _var, _val in vars_map.items():
            if _var in abs_vars:
                # Only expand abs vars if they appear as a call argument (bare
                # identifier inside a read/write call), not at assignment sites.
                # We detect this by checking if the var appears in read/write
                # function call syntax: fn_name(var  or  fn_name(var,
                if re.search(rf'\(\s*{re.escape(_var)}\s*[,)]', line) or re.search(rf'\(\s*{re.escape(_var)}\s*$', line):
                    _line_has_abs_var = True
                    _quoted_val = f'"{_val}"'
                    line = re.sub(rf'\b{re.escape(_var)}\b', lambda _m, _r=_quoted_val: _r, line)
                continue
            # Use a lambda so backslashes in _val are treated as literals, not
            # regex replacement escape sequences (e.g. C:\Users would be \U...).
            _quoted_val = f'"{_val}"'
            line = re.sub(rf'\b{re.escape(_var)}\b', lambda _m, _r=_quoted_val: _r, line)
        _join_force_abs = _join_force_abs or _line_has_abs_var

        # --- String division: "a" / "b" [/ "c"]* -> "a/b/c" (inline, after expansion) ---
        # Handles pd.read_csv(BASE / "input.csv") after BASE is expanded to "data"
        # Repeatedly apply to handle multi-segment chains.
        for _ in range(5):  # up to 5 passes for deep nesting
            _sdm = _STR_DIV_INLINE_RE.search(line)
            if not _sdm:
                break
            _full = _sdm.group(0)
            _base = _sdm.group(1)
            _divs = re.findall(r'/\s*"([^"]*?)"', _full)
            _resolved = '/'.join([_base] + _divs).replace('//', '/').replace('/./', '/')
            # Normalise ".." segments
            _parts = []
            for seg in _resolved.split('/'):
                if seg == '..':
                    if _parts:
                        _parts.pop()
                elif seg and seg != '.':
                    _parts.append(seg)
            _resolved = '/'.join(_parts)
            line = line.replace(_full, f'"{_resolved}"', 1)

        # --- String concatenation: "a" + "b" -> "ab" (inline, after variable expansion) ---
        # Handles pd.read_csv(base + "suffix") after base is expanded to "data/"
        # Fixed-point loop: repeat until no more adjacent quoted-string pairs remain
        # (single-pass finditer missed chained concatenations like "a" + "b" + "c").
        for _ in range(10):
            _cm = _STR_CONCAT_INLINE_RE.search(line)
            if not _cm:
                break
            _concat_result = _cm.group(1) + _cm.group(2)
            line = line.replace(_cm.group(0), f'"{_concat_result}"', 1)

        # --- Path helper: Path("a") / "b" [/ "c"]* (inline, after variable expansion) ---
        # After variable expansion, Path(var) becomes Path("resolved_val").
        # _PATH_DIV_INLINE_RE matches the full Path("a") / "b" / "c" expression.
        for _pdm in _PATH_DIV_INLINE_RE.finditer(line):
            _full_match = _pdm.group(0)
            # Extract base from Path("base")
            _base_m = re.match(r'\bPath\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')\s*\)', _full_match)
            if _base_m:
                _base = _base_m.group(1) or _base_m.group(2)
                # Extract all / "literal" parts after the Path(...)
                _suffix_parts = re.findall(r'/\s*(?:"([^"]+)"|\'([^\']+)\')', _full_match)
                _parts = [_base] + [p[0] or p[1] for p in _suffix_parts]
                _resolved = '/'.join(_parts)
                line = line.replace(_full_match, f'"{_resolved}"', 1)
                break  # one substitution per line

        # --- Fix A: transparent Path("val") unwrap (no / following) ---
        # After variable expansion, plt.savefig(Path("resolved")) becomes
        # plt.savefig("resolved") so that the savefig write pattern can match.
        # _PATH_WRAP_INLINE_RE uses a negative lookahead (?!\s*/) to avoid
        # conflicts with _PATH_DIV_INLINE_RE (which handles Path("a")/"b").
        for _pwm in _PATH_WRAP_INLINE_RE.finditer(line):
            _pw_val = _pwm.group(1) or _pwm.group(2)
            if _pw_val:
                line = line.replace(_pwm.group(0), f'"{_pw_val}"', 1)

        # --- os.listdir: directory-scan wildcard read ---
        # Recognises os.listdir(FOLDER) and emits a wildcard placeholder node.
        # If the next 10 lines contain .endswith(".ext"), use that extension.
        _listdir_m = _LISTDIR_RE.search(line)
        if _listdir_m:
            _ld_arg = _listdir_m.group(1).strip()
            # Resolve the folder argument: try vars_map, then partial join, then bare
            _ld_folder: str | None = None
            if _ld_arg in vars_map:
                _ld_folder = vars_map[_ld_arg]
            else:
                # Try treating the arg as an os.path.join expression inline
                _ld_joined, _ = _resolve_ospath_join(f'os.path.join({_ld_arg})', vars_map, abs_vars)
                if _ld_joined:
                    _ld_folder = _ld_joined
                else:
                    _ld_joined_p, _ = _resolve_ospath_join(
                        f'os.path.join({_ld_arg})', vars_map, abs_vars, partial_wildcard=True
                    )
                    if _ld_joined_p:
                        _ld_folder = _ld_joined_p
            if _ld_folder and not _ld_folder.endswith('/'):
                # Scan the current line and the next 10 raw lines for
                # .endswith(".ext") suffix hint (the filter may be inline
                # in the same list comprehension as the os.listdir call).
                _suffix_hint: str | None = None
                _lookahead = [raw_line] + raw_lines[line_no: line_no + 10]
                for _la_line in _lookahead:
                    _ew_m = _ENDSWITH_RE.search(_la_line)
                    if _ew_m:
                        _ext_val = _ew_m.group(1) or _ew_m.group(2)
                        if _ext_val and _ext_val.startswith('.'):
                            _suffix_hint = _ext_val
                        break
                _wildcard_node = _ld_folder.rstrip('/') + ('/*' + _suffix_hint if _suffix_hint else '/*')
                _add_event(line_no, 'open_read', _wildcard_node, is_write=False)

        # --- os.walk: recursive directory-scan wildcard read ---
        # Recognises `for root, dirs, files in os.walk(FOLDER):` and emits a
        # wildcard read edge FOLDER/**/*.{suffix} (or FOLDER/**/* if no suffix
        # filter is detectable within the next 10 lines).
        _oswalk_m = _OSWALK_RE.search(line)
        if _oswalk_m:
            _ow_arg = _oswalk_m.group(1).strip()
            _ow_folder: str | None = None
            if _ow_arg in vars_map:
                _ow_folder = vars_map[_ow_arg]
            else:
                _ow_joined, _ = _resolve_ospath_join(f'os.path.join({_ow_arg})', vars_map, abs_vars)
                if _ow_joined:
                    _ow_folder = _ow_joined
                else:
                    _ow_joined_p, _ = _resolve_ospath_join(
                        f'os.path.join({_ow_arg})', vars_map, abs_vars, partial_wildcard=True
                    )
                    if _ow_joined_p:
                        _ow_folder = _ow_joined_p
            if _ow_folder and not _ow_folder.endswith('/'):
                _suffix_hint_ow: str | None = None
                _lookahead_ow = [raw_line] + raw_lines[line_no: line_no + 10]
                for _la_line_ow in _lookahead_ow:
                    _ew_m_ow = _ENDSWITH_RE.search(_la_line_ow)
                    if _ew_m_ow:
                        _ext_val_ow = _ew_m_ow.group(1) or _ew_m_ow.group(2)
                        if _ext_val_ow and _ext_val_ow.startswith('.'):
                            _suffix_hint_ow = _ext_val_ow
                        break
                _wildcard_node_ow = _ow_folder.rstrip('/') + ('/**/*' + _suffix_hint_ow if _suffix_hint_ow else '/**/*')
                _add_event(line_no, 'os_walk', _wildcard_node_ow, is_write=False)

        # --- Two-line with open(VAR, "rb") as f: binary read via variable lookup ---
        # When the path is stored in a variable (not a literal), the standard
        # open_read regex cannot match.  We detect `with open(VAR, mode)` and
        # look VAR up in vars_map to emit a read edge.
        _wopen_m = _WITH_OPEN_VAR_RB_RE.search(line)
        if _wopen_m:
            _wopen_var = _wopen_m.group(1)
            _wopen_path = vars_map.get(_wopen_var)
            if _wopen_path:
                _add_event(line_no, 'open_read', _wopen_path, is_write=False)

        # --- Read patterns ---
        read_matched = False
        for command, pattern in read_patterns:
            raw = _try_match(pattern, line, vars_map)
            if raw is not None:
                # Also try variable expansion
                expanded = vars_map.get(raw, raw)
                _add_event(line_no, command, expanded, is_write=False, force_abs=_join_force_abs)
                read_matched = True
                break  # one read per line (first match)

        # --- Write patterns ---
        write_matched = False
        for command, pattern in write_patterns:
            raw = _try_match(pattern, line, vars_map)
            if raw is not None:
                expanded = vars_map.get(raw, raw)
                _add_event(line_no, command, expanded, is_write=True, force_abs=_join_force_abs)
                write_matched = True
                break  # one write per line (first match)

        # --- Fix B: kwarg path heuristic for user-defined functions ---
        # When a call passes a known path-keyword argument (filename=, output=,
        # output_path=, etc.) with a resolvable value, emit a write edge.
        # This fires even when no conventional write pattern matched, so that
        # calls like plot_and_save(..., filename=path) are captured.
        # Guard: only fire when the keyword appears AFTER an opening '(' on the
        # same line — this prevents matching VAR assignments like
        # filename = os.path.join(...) where 'filename' is the LHS, not a kwarg.
        if not write_matched:
            for _km in _KWARG_PATH_RE.finditer(line):
                # Require that there is an unmatched '(' before the match start
                _pre = line[:_km.start()]
                if _pre.count('(') <= _pre.count(')'):
                    continue  # match is not inside a function call
                # Groups: 1=keyword, 2=double-quoted literal, 3=single-quoted literal, 4=var name
                _kw_lit_d = _km.group(2)
                _kw_lit_s = _km.group(3)
                _kw_var   = _km.group(4)
                if _kw_lit_d is not None:
                    _kw_path = _kw_lit_d
                elif _kw_lit_s is not None:
                    _kw_path = _kw_lit_s
                elif _kw_var is not None:
                    _kw_path = vars_map.get(_kw_var)  # type: ignore[assignment]
                else:
                    _kw_path = None
                if _kw_path and _kw_path not in vars_map:
                    # Looks like a resolved path string (contains a dot or slash)
                    # Avoid emitting edges for plain variable names or short tokens
                    if '.' in _kw_path or '/' in _kw_path or '\\' in _kw_path:
                        _add_event(line_no, 'kwarg_write', _kw_path, is_write=True, force_abs=_join_force_abs)
                        write_matched = True
                        break  # one kwarg write per line

        # --- F-string partial placeholder (lower priority) ---
        # Only emit a placeholder when no concrete path was already found,
        # and only on lines that look like they pass data to a read/write call.
        if not read_matched and not write_matched:
            for fstr_m in _FSTRING_WITH_EXT_RE.finditer(raw_line):
                raw_fstr = fstr_m.group(0)
                placeholder = _extract_fstring_placeholder(raw_fstr)
                if placeholder:
                    # Guess write vs read: if the line contains "open" with a
                    # write-mode flag or a known write method, treat as write.
                    # Also treat f-strings ending in output-only extensions
                    # (.png, .pdf, .svg, .eps, .tex) as writes by default —
                    # these formats are almost never read back in, and this
                    # handles the two-line pattern where savefig appears on a
                    # separate line from the f-string assignment.
                    _write_ext = bool(re.search(
                        r'\.(png|pdf|svg|eps|tex)["\']', raw_fstr, re.I
                    ))
                    is_write = _write_ext or bool(re.search(
                        r'open\s*\([^)]*[,\s]["\'][wa]', raw_line, re.I
                    ) or re.search(
                        r'\.(to_csv|to_parquet|to_excel|to_json|to_feather|'
                        r'to_hdf|to_pickle|to_orc|to_stata|savefig|save)\s*\(',
                        raw_line, re.I,
                    ) or re.search(
                        r'\bpickle\.dump\b|\bjson\.dump\b|\bjoblib\.dump\b',
                        raw_line, re.I,
                    ))
                    _add_event(line_no, 'fstring_path', placeholder, is_write=is_write)
                    break  # one placeholder per line

    return ScriptParseResult(
        events=events,
        child_scripts=child_scripts,
        global_warnings=global_warnings,
        excluded_references=excluded_references,
    )
