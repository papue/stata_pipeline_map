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
# Comment stripping
# ---------------------------------------------------------------------------
_COMMENT_RE = re.compile(r'#.*$')

# ---------------------------------------------------------------------------
# External reference filter
# ---------------------------------------------------------------------------
_EXTERNAL_PREFIXES = ('http://', 'https://', 'ftp://', 's3://', 'gs://')

# ---------------------------------------------------------------------------
# Variable assignment:  name <- "value"  or  name = "value"
# ---------------------------------------------------------------------------
_VAR_ASSIGN_RE = re.compile(
    r'^\s*(\w+)\s*(?:<-|=)\s*(?:"([^"\\]*)"|\'([^\'\\]*)\')\s*$'
)

# Numeric assignment:  name <- 0.05  or  name = 42  (integer or float)
_VAR_ASSIGN_NUM_RE = re.compile(
    r'^\s*(\w+)\s*(?:<-|=)\s*(-?\d+(?:\.\d+)?)\s*$'
)

# ---------------------------------------------------------------------------
# Script-relative directory idioms (R's __file__ equivalents)
# Matches:  var <- dirname(sys.frame(1)$ofile)
#           var <- dirname(getSrcFilename(...))
#           var <- dirname(rstudioapi::getActiveDocumentContext()$path)
#           var <- tryCatch(dirname(sys.frame(1)$ofile), ...)  — first branch
# ---------------------------------------------------------------------------
_SCRIPT_DIR_RE = re.compile(
    r'^\s*(\w+)\s*(?:<-|=)\s*'
    r'(?:tryCatch\s*\(\s*)?'  # optional tryCatch(
    r'dirname\s*\('
    r'(?:'
    r'sys\.frame\s*\([^)]*\)\s*\$ofile'
    r'|getSrcFilename\s*\([^)]*\)'
    r'|rstudioapi::getActiveDocumentContext\s*\(\s*\)\s*\$path'
    r')',
    re.I,
)

# getSrcFilename assigned directly (two-step: script_path <- getSrcFilename(...); script_dir <- dirname(script_path))
_GETSRCFILENAME_RE = re.compile(
    r'^\s*(\w+)\s*(?:<-|=)\s*getSrcFilename\s*\(',
    re.I,
)

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------
# here("a", "b", "c")  or  here::here("a", "b")
_HERE_RE = re.compile(r'\bhere(?:::here)?\s*\(([^)]+)\)', re.I)
# file.path("a", var, "c")
_FILEPATH_RE = re.compile(r'\bfile\.path\s*\(([^)]+)\)', re.I)
# paste0("a", var, "b")
_PASTE0_RE = re.compile(r'\bpaste0\s*\(([^)]+)\)', re.I)
# paste("a", var, sep="/")  — separator-based join
_PASTE_SEP_RE = re.compile(r'\bpaste\s*\(([^)]+)\)', re.I)
# sprintf("template/%s/file.csv", arg1, arg2, ...)  — one or more placeholders
_SPRINTF_RE = re.compile(r'\bsprintf\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')\s*,\s*(.+)\)\s*$', re.I)
# glue("path/{var}.png")  — R glue package string interpolation
_GLUE_RE = re.compile(r'\bglue\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')\s*\)', re.I)
# fs::path("a", var, "b") — same semantics as file.path
_FS_PATH_RE = re.compile(r'\bfs::path\s*\(([^)]+)\)', re.I)

# ---------------------------------------------------------------------------
# Pattern: list.files(path, ...)  — directory-scan read (R analogue of os.listdir/os.walk)
# Captures the first positional argument (a path string or variable).
# If the call contains  pattern="\\.ext$"  we infer the suffix filter.
# ---------------------------------------------------------------------------
_LIST_FILES_RE = re.compile(r'\blist\.files\s*\(([^)]+)\)', re.I)
# Detect suffix in pattern= arg inside the same list.files() call or nearby lines
_LIST_FILES_PATTERN_RE = re.compile(r'\bpattern\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)
# Simple extension heuristic: match the last \.\w+ or \.\w+ in the pattern string
_EXT_FROM_PATTERN_RE = re.compile(r'\\\.(\w+)')

# ---------------------------------------------------------------------------
# Quoted string extraction
# ---------------------------------------------------------------------------
_QUOTED_RE = re.compile(r'(?:"([^"\\]+)"|\'([^\'\\]+)\')')

# ---------------------------------------------------------------------------
# Kwarg heuristic: function calls with path-like keyword argument names
# Used to detect write side-effects in user-defined function calls.
# ---------------------------------------------------------------------------
_PATH_KWARG_NAMES = frozenset({'filename', 'file', 'path', 'output', 'save_to', 'filepath', 'con'})
# Matches: kwarg_name = "some/path.ext"  (after variable expansion)
_KWARG_PATH_RE = re.compile(
    r'\b(' + '|'.join(re.escape(k) for k in sorted(_PATH_KWARG_NAMES)) + r')\s*=\s*(?:"([^"]+)"|\'([^\']+)\')',
    re.I,
)

# ---------------------------------------------------------------------------
# READ patterns: (command_label, regex)
# Groups 1 and 2 capture alternative double/single quoted path.
# ---------------------------------------------------------------------------
# For functions where the path is the FIRST positional arg
_READS_FIRST_ARG: list[tuple[str, re.Pattern[str]]] = [
    # base R
    ('read_csv',   re.compile(r'\bread\.csv\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_csv2',  re.compile(r'\bread\.csv2\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_table', re.compile(r'\bread\.table\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_delim', re.compile(r'\bread\.delim\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('readRDS',    re.compile(r'\breadRDS\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('load',       re.compile(r'\bload\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # readr (qualified and unqualified)
    ('read_csv_readr',   re.compile(r'\bread_csv\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_csv2_readr',  re.compile(r'\bread_csv2\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_delim_readr', re.compile(r'\bread_delim\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_rds',         re.compile(r'\bread_rds\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_tsv',         re.compile(r'\bread_tsv\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # readxl
    ('read_excel', re.compile(r'\bread_excel\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_xls',   re.compile(r'\bread_xls\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_xlsx',  re.compile(r'\bread_xlsx\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # haven
    ('read_dta',  re.compile(r'\bread_dta\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_sas',  re.compile(r'\bread_sas\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_spss', re.compile(r'\bread_spss\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_sav',  re.compile(r'\bread_sav\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # data.table
    ('fread', re.compile(r'\bfread\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # arrow / feather
    ('read_parquet', re.compile(r'\bread_parquet\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_feather', re.compile(r'\bread_feather\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # jsonlite
    ('fromJSON', re.compile(r'\bfromJSON\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # sf (spatial)
    ('st_read',    re.compile(r'\bst_read\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('st_read_ns', re.compile(r'\bsf::st_read\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # rvest
    ('read_html', re.compile(r'\bread_html\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # openxlsx
    ('read.xlsx',    re.compile(r'\bread\.xlsx\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('loadWorkbook', re.compile(r'\bloadWorkbook\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # fst
    ('read.fst', re.compile(r'\bread\.fst\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('read_fst', re.compile(r'\bread_fst\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
]

# For readRDS with file= keyword argument
_READRDS_KW_RE = re.compile(r'\breadRDS\s*\(.*?\bfile\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)

# ---------------------------------------------------------------------------
# WRITE patterns
# ---------------------------------------------------------------------------

# Writes where the path is the SECOND positional arg: func(data, "path")
_WRITES_DATA_THEN_PATH: list[tuple[str, re.Pattern[str]]] = [
    # base R
    ('write_csv',   re.compile(r'\bwrite\.csv\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('write_csv2',  re.compile(r'\bwrite\.csv2\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('write_table', re.compile(r'\bwrite\.table\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('saveRDS',     re.compile(r'\bsaveRDS\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # readr
    ('write_csv_readr',  re.compile(r'\bwrite_csv\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('write_csv2_readr', re.compile(r'\bwrite_csv2\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('write_tsv',        re.compile(r'\bwrite_tsv\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('write_delim',      re.compile(r'\bwrite_delim\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('write_rds',        re.compile(r'\bwrite_rds\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # writexl
    ('write_xlsx', re.compile(r'\bwrite_xlsx\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # data.table
    ('fwrite', re.compile(r'\bfwrite\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # haven
    ('write_dta', re.compile(r'\bwrite_dta\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('write_sav', re.compile(r'\bwrite_sav\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('write_sas', re.compile(r'\bwrite_sas\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # arrow
    ('write_parquet', re.compile(r'\bwrite_parquet\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('write_feather', re.compile(r'\bwrite_feather\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # sf (spatial)
    ('st_write',    re.compile(r'\bst_write\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('st_write_ns', re.compile(r'\bsf::st_write\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # tmap (positional form)
    ('tmap_save', re.compile(r'\btmap_save\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # htmlwidgets (positional form)
    ('saveWidget', re.compile(r'\bsaveWidget\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # writeLines (positional form) — first arg must NOT be c(...) to avoid false positives
    # from c("line1","line2") where the comma inside c() looks like a second arg boundary
    ('writeLines', re.compile(r'\bwriteLines\s*\((?!c\s*\()[^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # openxlsx
    ('write.xlsx',    re.compile(r'\bwrite\.xlsx\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('saveWorkbook',  re.compile(r'\bsaveWorkbook\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # fst
    ('write.fst', re.compile(r'\bwrite\.fst\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
]

# Writes with keyword argument: file="path" or filename="path"
_WRITES_KEYWORD: list[tuple[str, re.Pattern[str]]] = [
    # saveRDS(data, file="path")
    ('saveRDS_kw', re.compile(r'\bsaveRDS\s*\(.*?\bfile\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # save(..., file="path")
    ('save_rdata', re.compile(r'\bsave\s*\(.*?\bfile\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # ggsave("path") — path is first arg
    ('ggsave',     re.compile(r'\bggsave\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # ggsave(filename="path")
    ('ggsave_kw',  re.compile(r'\bggsave\s*\(.*?\bfilename\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # graphics devices: pdf/png/svg/jpeg/tiff — first positional or filename= keyword
    ('pdf',     re.compile(r'\bpdf\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('pdf_kw',  re.compile(r'\bpdf\s*\(.*?\bfilename\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('png',     re.compile(r'\bpng\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('png_kw',  re.compile(r'\bpng\s*\(.*?\bfilename\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('svg',     re.compile(r'\bsvg\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('svg_kw',  re.compile(r'\bsvg\s*\(.*?\bfilename\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('jpeg',    re.compile(r'\bjpeg\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('jpeg_kw', re.compile(r'\bjpeg\s*\(.*?\bfilename\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('tiff',    re.compile(r'\btiff\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('tiff_kw', re.compile(r'\btiff\s*\(.*?\bfilename\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # jsonlite
    ('write_json', re.compile(r'\bwrite_json\s*\([^,]+,\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('toJSON_write', re.compile(r'\btoJSON\s*\(.*?\bpath\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # tmap (keyword form)
    ('tmap_save_kw', re.compile(r'\btmap_save\s*\(.*?\bfilename\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # htmlwidgets (keyword form)
    ('saveWidget_kw', re.compile(r'\bsaveWidget\s*\(.*?\bfile\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # writeLines (keyword form)
    ('writeLines_kw', re.compile(r'\bwriteLines\s*\(.*?\bcon\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # writexl::write_xlsx(df, path="path")
    ('write_xlsx_kw', re.compile(r'\bwrite_xlsx\s*\(.*?\bpath\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # arrow::write_parquet(df, sink="path")
    ('write_parquet_kw', re.compile(r'\bwrite_parquet\s*\(.*?\bsink\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    # cat(..., file="path") and message(..., file="path")
    ('cat_file',     re.compile(r'\bcat\s*\(.*?\bfile\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
    ('message_file', re.compile(r'\bmessage\s*\(.*?\bfile\s*=\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)),
]

# ---------------------------------------------------------------------------
# Script call patterns
# ---------------------------------------------------------------------------
_SOURCE_RE = re.compile(r'\bsource\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)
_SYS_SOURCE_RE = re.compile(r'\bsys\.source\s*\(\s*(?:"([^"]+)"|\'([^\']+)\')', re.I)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _join_continued_lines(lines: list[str]) -> list[str]:
    """
    Join lines where parentheses are not yet closed so that multi-line
    function calls become a single logical line.  Each joined line keeps
    the line-number of the FIRST physical line (the rest are replaced with
    empty strings so line counts stay correct).
    """
    result: list[str] = []
    buf = ''
    depth = 0
    for raw in lines:
        # Strip comment for paren-counting but keep original for result
        stripped = _strip_comment(raw)
        for ch in stripped:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
        if buf:
            buf = buf.rstrip() + ' ' + raw.strip()
        else:
            buf = raw
        if depth <= 0:
            result.append(buf)
            buf = ''
            depth = 0
        else:
            # Will be consumed by next line; emit empty placeholder
            result.append('')
    if buf:
        result.append(buf)
    return result


def _strip_comment(line: str) -> str:
    """Remove R # comments, handling basic string literal detection."""
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


def _extract_quoted_args(args_text: str) -> list[str | None]:
    """Extract a list of string values from comma-separated args text.
    Returns None for each arg that is not a plain quoted string."""
    result = []
    for piece in args_text.split(','):
        piece = piece.strip()
        m = _QUOTED_RE.match(piece)
        if m:
            result.append(m.group(1) or m.group(2))
        else:
            result.append(piece if piece else None)  # keep var name for expansion
    return result


def _resolve_path_args(args_text: str, vars_map: dict[str, str]) -> str | None:
    """Resolve a comma-separated list of path components to a joined path."""
    parts = []
    for piece in args_text.split(','):
        piece = piece.strip()
        if not piece:
            continue
        m = _QUOTED_RE.match(piece)
        if m:
            parts.append(m.group(1) or m.group(2))
        elif piece in vars_map:
            parts.append(vars_map[piece])
        else:
            return None  # unresolvable component
    result = '/'.join(parts) if parts else None
    # Guard: if the resolved result is a bare directory reference (e.g. ".",
    # "./" or any path ending with "/"), discard it — it has no filename
    # component and would produce a spurious directory node.
    if result is not None:
        stripped = result.rstrip('/')
        if stripped in ('', '.', '..') or result.endswith('/') or result.endswith('\\'):
            return None
    return result


def _resolve_path_args_partial(args_text: str, vars_map: dict[str, str]) -> tuple[str, bool]:
    """Resolve path components (for file.path / here), substituting {varname} for unknown variables.
    Parts are joined with '/' like a file path.

    Returns (path_string, is_partial) where is_partial=True if any component
    was unresolvable and a placeholder was inserted.
    """
    parts = []
    is_partial = False
    for piece in args_text.split(','):
        piece = piece.strip()
        if not piece:
            continue
        m = _QUOTED_RE.match(piece)
        if m:
            parts.append(m.group(1) or m.group(2))
        elif piece in vars_map:
            parts.append(vars_map[piece])
        else:
            # Unknown variable — use {varname} placeholder
            parts.append(f'{{{piece}}}')
            is_partial = True
    path = '/'.join(parts) if parts else ''
    return path, is_partial


def _resolve_concat_args_partial(args_text: str, vars_map: dict[str, str]) -> tuple[str, bool]:
    """Resolve concatenation args (for paste0), substituting {varname} for unknown variables.
    Parts are concatenated with no separator (like paste0 behaviour).

    Returns (result_string, is_partial) where is_partial=True if any component
    was unresolvable and a placeholder was inserted.
    """
    parts = []
    is_partial = False
    for piece in args_text.split(','):
        piece = piece.strip()
        if not piece:
            continue
        m = _QUOTED_RE.match(piece)
        if m:
            parts.append(m.group(1) or m.group(2))
        elif piece in vars_map:
            parts.append(vars_map[piece])
        else:
            # Unknown variable — use {varname} placeholder
            parts.append(f'{{{piece}}}')
            is_partial = True
    result = ''.join(parts) if parts else ''
    return result, is_partial


def _extract_balanced_args(text: str, func_name: str) -> list[str]:
    """Extract the top-level args string from a function call like func_name(...),
    handling nested parentheses correctly.

    Returns a list of (start_idx, end_idx, args_text) for each match found.
    Returns [] if no match.
    """
    results = []
    pattern = re.compile(r'\b' + re.escape(func_name) + r'\s*\(', re.I)
    for m in pattern.finditer(text):
        start = m.end()  # position after '('
        depth = 1
        i = start
        while i < len(text) and depth > 0:
            if text[i] == '(':
                depth += 1
            elif text[i] == ')':
                depth -= 1
            i += 1
        if depth == 0:
            results.append((m.start(), i, text[start:i - 1]))
    return results


def _split_top_level_args(args_text: str) -> list[str]:
    """Split args_text by commas at the top level only (not inside nested parens/quotes)."""
    parts = []
    current = []
    depth = 0
    in_single = False
    in_double = False
    for ch in args_text:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif not in_single and not in_double:
            if ch == '(':
                depth += 1
            elif ch == ')':
                depth -= 1
            elif ch == ',' and depth == 0:
                parts.append(''.join(current).strip())
                current = []
                continue
        current.append(ch)
    if current:
        parts.append(''.join(current).strip())
    return parts


def _resolve_paste0_args(args_text: str, vars_map: dict[str, str]) -> tuple[str | None, bool]:
    """Resolve paste0() args by concatenating directly (no separator).

    Handles nested paste0/file.path/here calls if already substituted.
    Returns (result, is_partial). is_partial=True means a placeholder was used.
    Returns (None, False) if empty.
    """
    parts_raw = _split_top_level_args(args_text)
    parts = []
    is_partial = False
    for piece in parts_raw:
        if not piece:
            continue
        m = _QUOTED_RE.match(piece)
        if m:
            parts.append(m.group(1) or m.group(2))
        elif piece in vars_map:
            parts.append(vars_map[piece])
        else:
            parts.append(f'{{{piece}}}')
            is_partial = True
    result = ''.join(parts) if parts else ''
    return (result if result else None), is_partial


def _resolve_paste_sep_args(args_text: str, vars_map: dict[str, str]) -> tuple[str | None, bool]:
    """Resolve paste() args with a sep= keyword argument.

    paste(a, b, sep="/")  ->  a + "/" + b
    Returns (result, is_partial). Returns (None, False) if no sep= or empty result.
    """
    parts_raw = _split_top_level_args(args_text)
    sep = ' '  # default R paste separator
    pos_parts: list[str] = []
    is_partial = False

    for piece in parts_raw:
        # Check for sep= keyword argument
        sep_m = re.match(r'^sep\s*=\s*(?:"([^"\\]*)"|\'([^\'\\]*)\')\s*$', piece)
        if sep_m:
            sep = sep_m.group(1) if sep_m.group(1) is not None else sep_m.group(2)
            continue
        # Skip other keyword args (collapse=, etc.)
        if re.match(r'^\w+\s*=', piece):
            continue
        m = _QUOTED_RE.match(piece)
        if m:
            pos_parts.append(m.group(1) or m.group(2))
        elif piece in vars_map:
            pos_parts.append(vars_map[piece])
        else:
            pos_parts.append(f'{{{piece}}}')
            is_partial = True

    # Only return a result if the separator makes it look like a path
    if not pos_parts:
        return None, False
    result = sep.join(pos_parts)
    return (result if result else None), is_partial


def _resolve_here(line: str, vars_map: dict[str, str]) -> list[str]:
    """Resolve here() / here::here() calls."""
    results = []
    for m in _HERE_RE.finditer(line):
        resolved = _resolve_path_args(m.group(1), vars_map)
        if resolved:
            results.append((m.start(), m.end(), resolved))
    # Return paths only
    return [r for _, _, r in results]


def _resolve_filepath(line: str, vars_map: dict[str, str]) -> list[str]:
    """Resolve file.path() calls."""
    results = []
    for m in _FILEPATH_RE.finditer(line):
        resolved = _resolve_path_args(m.group(1), vars_map)
        if resolved:
            results.append(resolved)
    return results


def _resolve_paste0(line: str, vars_map: dict[str, str]) -> list[str]:
    """Resolve paste0() calls using balanced-paren extraction and direct concatenation."""
    results = []
    for _start, _end, args_text in _extract_balanced_args(line, 'paste0'):
        resolved, _partial = _resolve_paste0_args(args_text, vars_map)
        if resolved and not _partial and ('.' in resolved or '/' in resolved):
            results.append(resolved)
    return results


def _resolve_paste_sep(line: str, vars_map: dict[str, str]) -> list[str]:
    """Resolve paste(a, b, sep='/') calls using balanced-paren extraction."""
    results = []
    for _start, _end, args_text in _extract_balanced_args(line, 'paste'):
        resolved, _partial = _resolve_paste_sep_args(args_text, vars_map)
        if resolved and not _partial and ('.' in resolved or '/' in resolved):
            results.append(resolved)
    return results


def _resolve_sprintf(line: str, vars_map: dict[str, str]) -> list[str]:
    """Resolve sprintf("template/%s/%s/file.csv", arg1, arg2, ...) with multiple placeholders."""
    results = []
    for m in _SPRINTF_RE.finditer(line):
        template = m.group(1) or m.group(2)
        args_text = (m.group(3) or '').strip()
        # Count total format specifiers (%s, %d, %f, %i, %g)
        placeholders = re.findall(r'%[-+]?\d*\.?\d*[sdfig]', template)
        if not placeholders:
            continue
        # Split args by comma, resolve each
        raw_args = [a.strip() for a in args_text.split(',')]
        if len(raw_args) < len(placeholders):
            continue  # not enough args
        subs = []
        ok = True
        for i, ph in enumerate(placeholders):
            arg = raw_args[i] if i < len(raw_args) else ''
            quoted_m = _QUOTED_RE.match(arg)
            if quoted_m:
                subs.append(quoted_m.group(1) or quoted_m.group(2))
            elif arg in vars_map:
                subs.append(vars_map[arg])
            else:
                ok = False
                break
        if not ok:
            continue
        result = template
        for sub in subs:
            result = re.sub(r'%[-+]?\d*\.?\d*[sdfig]', sub, result, count=1)
        results.append(result)
    return results


def _resolve_glue(line: str, vars_map: dict[str, str]) -> list[str]:
    """Resolve glue("path/{var}.png") calls by substituting {varname} tokens.

    R glue() uses {varname} interpolation.  Substitutes known vars from vars_map;
    if a variable is unknown a placeholder token {varname} is kept in the result.
    Returns a list of resolved path strings (fully resolved only).
    """
    results = []
    for m in _GLUE_RE.finditer(line):
        template = m.group(1) if m.group(1) is not None else m.group(2)
        if not template:
            continue
        # Substitute each {varname} token
        result = template
        unresolved = False

        def _sub_glue_var(vm: re.Match[str]) -> str:
            nonlocal unresolved
            vname = vm.group(1)
            if vname in vars_map:
                return vars_map[vname]
            unresolved = True
            return vm.group(0)  # keep placeholder

        result = re.sub(r'\{(\w+)\}', _sub_glue_var, result)
        if not unresolved and ('.' in result or '/' in result):
            results.append(result)
    return results


def _try_match(pattern: re.Pattern[str], line: str, vars_map: dict[str, str]) -> str | None:
    m = pattern.search(line)
    if not m:
        return None
    raw = m.group(1) if m.group(1) is not None else m.group(2)
    if raw is None:
        return None
    return vars_map.get(raw, raw)


def _apply_balanced_substitutions(line: str, vars_map: dict[str, str], allow_partial: bool = False) -> tuple[str, bool]:
    """
    Replace paste0(...), paste(..., sep=...), file.path(...), here(...) and sprintf(...)
    calls in line with their resolved quoted equivalents.

    Uses balanced-parenthesis extraction so that nested calls are handled correctly:
    inner-most calls are substituted first, then outer calls see the already-resolved strings.

    Returns (modified_line, was_partial).  was_partial is True when allow_partial=True
    and at least one placeholder {varname} was inserted.
    """
    was_partial = False

    # Iterate until no more substitutions are made (handles nesting)
    for _iteration in range(5):
        changed = False

        # --- paste0(...) — concatenate with no separator ---
        for start, end, args_text in reversed(_extract_balanced_args(line, 'paste0')):
            resolved, partial = _resolve_paste0_args(args_text, vars_map)
            if resolved is not None and (allow_partial or not partial):
                if '.' in resolved or '/' in resolved or (allow_partial and '{' in resolved):
                    if partial:
                        was_partial = True
                    line = line[:start] + f'"{resolved}"' + line[end:]
                    changed = True

        # --- paste(..., sep=...) — join with separator ---
        for start, end, args_text in reversed(_extract_balanced_args(line, 'paste')):
            # Skip if it looks like paste0 (already handled) — check by peeking at char before '('
            if start > 0 and line[start - 1] == '0':
                continue
            # Only handle when sep= is present and sep is '/' (path-like separator)
            if 'sep' not in args_text:
                continue
            resolved, partial = _resolve_paste_sep_args(args_text, vars_map)
            if resolved is not None and (allow_partial or not partial):
                if '.' in resolved or '/' in resolved or (allow_partial and '{' in resolved):
                    if partial:
                        was_partial = True
                    line = line[:start] + f'"{resolved}"' + line[end:]
                    changed = True

        # --- file.path(...) ---
        for start, end, args_text in reversed(_extract_balanced_args(line, 'file.path')):
            if allow_partial:
                path, partial = _resolve_path_args_partial(args_text, vars_map)
            else:
                path = _resolve_path_args(args_text, vars_map)
                partial = False
            if path and (allow_partial or not partial):
                if partial:
                    was_partial = True
                line = line[:start] + f'"{path}"' + line[end:]
                changed = True

        # --- fs::path(...) — same slash-join semantics as file.path ---
        for start, end, args_text in reversed(_extract_balanced_args(line, 'fs::path')):
            if allow_partial:
                path, partial = _resolve_path_args_partial(args_text, vars_map)
            else:
                path = _resolve_path_args(args_text, vars_map)
                partial = False
            if path and (allow_partial or not partial):
                if partial:
                    was_partial = True
                line = line[:start] + f'"{path}"' + line[end:]
                changed = True

        # --- here(...) / here::here(...) ---
        # Use the original _HERE_RE regex (which handles the '::here' qualifier) instead
        # of _extract_balanced_args to avoid matching 'here' inside 'here::here'.
        def _sub_here_in_balanced(m: re.Match[str]) -> str:
            nonlocal was_partial, changed
            args = m.group(1)
            if allow_partial:
                path_r, partial_r = _resolve_path_args_partial(args, vars_map)
            else:
                path_r = _resolve_path_args(args, vars_map)
                partial_r = False
            if path_r and (allow_partial or not partial_r):
                if partial_r:
                    was_partial = True
                changed = True
                return f'"{path_r}"'
            return m.group(0)

        new_line = _HERE_RE.sub(_sub_here_in_balanced, line)
        if new_line != line:
            line = new_line

        # --- glue("path/{var}") — R glue package interpolation ---
        def _sub_glue(gm: re.Match[str]) -> str:
            nonlocal was_partial, changed
            template = gm.group(1) if gm.group(1) is not None else gm.group(2)
            if not template:
                return gm.group(0)
            _unresolved = False

            def _sub_var(vm: re.Match[str]) -> str:
                nonlocal _unresolved
                vname = vm.group(1)
                if vname in vars_map:
                    return vars_map[vname]
                _unresolved = True
                return vm.group(0)

            result = re.sub(r'\{(\w+)\}', _sub_var, template)
            if _unresolved:
                if allow_partial:
                    was_partial = True
                    changed = True
                    return f'"{result}"'
                return gm.group(0)
            if '.' in result or '/' in result:
                changed = True
                return f'"{result}"'
            return gm.group(0)

        new_line = _GLUE_RE.sub(_sub_glue, line)
        if new_line != line:
            line = new_line

        # --- sprintf(...) ---
        new_line = _SPRINTF_RE.sub(
            lambda m: _replace_sprintf(m, vars_map),
            line,
        )
        if new_line != line:
            line = new_line
            changed = True

        if not changed:
            break

    return line, was_partial


def _replace_sprintf(m: re.Match[str], vars_map: dict[str, str]) -> str:
    """Replacement callback for sprintf in _apply_balanced_substitutions."""
    template = m.group(1) or m.group(2)
    args_text = (m.group(3) or '').strip()
    placeholders = re.findall(r'%[-+]?\d*\.?\d*[sdfig]', template)
    if not placeholders:
        return m.group(0)
    raw_args = [a.strip() for a in args_text.split(',')]
    if len(raw_args) < len(placeholders):
        return m.group(0)
    subs = []
    for i, _ in enumerate(placeholders):
        arg = raw_args[i] if i < len(raw_args) else ''
        quoted_m = _QUOTED_RE.match(arg)
        if quoted_m:
            subs.append(quoted_m.group(1) or quoted_m.group(2))
        elif arg in vars_map:
            subs.append(vars_map[arg])
        else:
            return m.group(0)
    result = template
    for sub in subs:
        result = re.sub(r'%[-+]?\d*\.?\d*[sdfig]', sub, result, count=1)
    return f'"{result}"'


def _preprocess_helpers(line: str, vars_map: dict[str, str]) -> tuple[str, list[str]]:
    """
    Replace path helper calls in line with their resolved quoted equivalents.
    Returns (modified_line, list_of_standalone_paths).
    Standalone paths come from helper calls that aren't embedded in a read/write call.
    """
    standalone: list[str] = []
    line, _ = _apply_balanced_substitutions(line, vars_map, allow_partial=False)
    return line, standalone


def _preprocess_helpers_partial(line: str, vars_map: dict[str, str]) -> tuple[str, bool]:
    """
    Like _preprocess_helpers but substitutes {varname} for unresolvable components
    instead of leaving the original expression in place.

    Returns (modified_line, was_partial) where was_partial=True if any placeholder
    was inserted.
    """
    return _apply_balanced_substitutions(line, vars_map, allow_partial=True)


# ---------------------------------------------------------------------------
# Main parser
# ---------------------------------------------------------------------------

def parse_r_file(
    project_root: Path,
    r_file: Path,
    exclusions: ExclusionConfig,
    normalization: NormalizationConfig,
    parser_config: ParserConfig,
    inherited_vars: dict[str, str] | None = None,
) -> ScriptParseResult:
    try:
        text = r_file.read_text(encoding='utf-8', errors='replace')
    except OSError:
        return ScriptParseResult(events=[], child_scripts=[], global_warnings=[])

    raw_lines = text.splitlines()
    rel_script, _ = to_project_relative(project_root, r_file, normalization)
    rel_script = normalize_token(rel_script)

    # Join multi-line function calls into single logical lines
    joined_lines = _join_continued_lines(raw_lines)

    # --- Pre-pass: collect variable assignments ---
    # Seed with inherited variables from caller (cross-script propagation),
    # then with the script's own directory (__file__ equivalents).
    # Local definitions override inherited ones.
    vars_map: dict[str, str] = dict(inherited_vars) if inherited_vars else {}
    script_dir_str = str(r_file.parent).replace('\\', '/')
    vars_map['__script_dir__'] = script_dir_str

    # First pass: collect literal string assignments and numeric assignments
    for line in joined_lines:
        clean = _strip_comment(line)
        m = _VAR_ASSIGN_RE.match(clean)
        if m:
            val = m.group(2) if m.group(2) is not None else m.group(3)
            vars_map[m.group(1)] = val
            continue
        # Also track numeric assignments (e.g. alpha <- 0.05) so sprintf can use them
        mn = _VAR_ASSIGN_NUM_RE.match(clean)
        if mn:
            vars_map[mn.group(1)] = mn.group(2)

    # Second pass: resolve script-dir idioms and function-call RHS assignments
    # Repeat a few times to handle chained assignments (script_path -> script_dir -> path)
    for _iteration in range(3):
        for line in joined_lines:
            clean = _strip_comment(line)
            # Pattern: var <- dirname(sys.frame(1)$ofile)  etc.
            m = _SCRIPT_DIR_RE.match(clean)
            if m:
                vars_map[m.group(1)] = script_dir_str
                continue
            # Pattern: var <- getSrcFilename(...) — evaluates to the script's path
            m = _GETSRCFILENAME_RE.match(clean)
            if m:
                vars_map[m.group(1)] = str(r_file).replace('\\', '/')
                continue
            # Pattern: var <- dirname(some_var) where some_var is already resolved
            m_dir = re.match(r'^\s*(\w+)\s*(?:<-|=)\s*dirname\s*\(\s*(\w+)\s*\)', clean)
            if m_dir:
                src_var = m_dir.group(2)
                if src_var in vars_map:
                    from pathlib import PurePosixPath
                    vars_map[m_dir.group(1)] = str(PurePosixPath(vars_map[src_var]).parent)
                continue
            # Pattern: var <- paste0(...)  — store resolved value
            # Use _apply_balanced_substitutions so nested paste0 calls are resolved
            # inner-first (e.g. paste0(paste0(base, "/sub"), "/file.csv")).
            m_assign = re.match(r'^\s*(\w+)\s*(?:<-|=)\s*(paste0\s*\()', clean)
            if m_assign:
                varname = m_assign.group(1)
                # Expand known vars (excluding the LHS varname to avoid corrupting the assignment)
                expanded = clean
                for _v, _val in vars_map.items():
                    if _v == varname:
                        continue  # do not expand the varname being assigned
                    expanded = re.sub(rf'\b{re.escape(_v)}\b', f'"{_val}"', expanded)
                resolved_line, _partial = _apply_balanced_substitutions(expanded, vars_map, allow_partial=False)
                # Extract the RHS of the assignment as a quoted string
                rhs_m = re.match(r'^\s*\w+\s*(?:<-|=)\s*"([^"]+)"\s*$', resolved_line)
                if rhs_m and not _partial:
                    vars_map[varname] = rhs_m.group(1)
                elif varname not in vars_map:
                    # Fall back to old approach for simple non-nested cases (only if not yet set)
                    paste_start = clean.index('paste0')
                    resolved_list = _resolve_paste0(clean[paste_start:], vars_map)
                    if resolved_list:
                        vars_map[varname] = resolved_list[0]
                continue
            # Pattern: var <- paste(..., sep=...)  — store resolved value
            m_assign_p = re.match(r'^\s*(\w+)\s*(?:<-|=)\s*paste\s*\(', clean)
            if m_assign_p and 'sep' in clean:
                resolved_list = _resolve_paste_sep(clean, vars_map)
                if resolved_list:
                    vars_map[m_assign_p.group(1)] = resolved_list[0]
                continue
            # Pattern: var <- sprintf(...)  — store resolved value
            m_assign2 = re.match(r'^\s*(\w+)\s*(?:<-|=)\s*(sprintf\s*\()', clean)
            if m_assign2:
                sp_start = clean.index('sprintf')
                resolved_list = _resolve_sprintf(clean[sp_start:], vars_map)
                if resolved_list:
                    vars_map[m_assign2.group(1)] = resolved_list[0]
                continue
            # Pattern: var <- glue("path/{var}")  — store resolved value
            m_glue = re.match(r'^\s*(\w+)\s*(?:<-|=)\s*glue\s*\(', clean, re.I)
            if m_glue:
                varname = m_glue.group(1)
                glue_paths = _resolve_glue(clean, vars_map)
                if glue_paths:
                    vars_map[varname] = glue_paths[0]
                continue
            # Pattern: var <- file.path(...)  — store resolved value
            m_assign3 = re.match(r'^\s*(\w+)\s*(?:<-|=)\s*(file\.path\s*\()', clean, re.I)
            if m_assign3:
                fp_start = clean.lower().index('file.path')
                resolved_list = _resolve_filepath(clean[fp_start:], vars_map)
                if resolved_list:
                    vars_map[m_assign3.group(1)] = resolved_list[0]
                continue
            # Pattern: var <- fs::path(...)  — same as file.path, slash-joined
            m_fspath = re.match(r'^\s*(\w+)\s*(?:<-|=)\s*fs::path\s*\(', clean, re.I)
            if m_fspath:
                varname = m_fspath.group(1)
                matches = _extract_balanced_args(clean, 'fs::path')
                if matches:
                    _, _, args_text = matches[0]
                    resolved = _resolve_path_args(args_text, vars_map)
                    if resolved:
                        vars_map[varname] = resolved
                continue
            # Pattern: var <- normalizePath(other_var, ...)
            # normalizePath is transparent for static analysis — propagate other_var's value
            m_norm = re.match(r'^\s*(\w+)\s*(?:<-|=)\s*normalizePath\s*\(\s*(\w+)', clean, re.I)
            if m_norm:
                varname = m_norm.group(1)
                src_var = m_norm.group(2)
                if src_var in vars_map:
                    vars_map[varname] = vars_map[src_var]
                continue
            # Pattern: var <- here(...)  or  var <- here::here(...)
            m_here = re.match(r'^\s*(\w+)\s*(?:<-|=)\s*here(?:::here)?\s*\(', clean, re.I)
            if m_here:
                varname = m_here.group(1)
                here_paths = _resolve_here(clean, vars_map)
                if here_paths:
                    vars_map[varname] = here_paths[0]
                continue

    # --- Partial vars pass: collect assignments that are partially resolvable ---
    # These feed the partial-resolution write path (loop variables etc.)
    # Strategy: apply _preprocess_helpers_partial to the full line, then check if the
    # result contains a simple var <- "partial_path" assignment pattern.
    _VAR_ASSIGN_QUOTED_RE = re.compile(
        r'^\s*(\w+)\s*(?:<-|=)\s*(?:"([^"]+)"|\'([^\']+)\')\s*$'
    )
    partial_vars_map: dict[str, str] = {}
    for line in joined_lines:
        clean = _strip_comment(line)
        # Only process lines that look like var assignments with path helpers
        if not re.match(r'^\s*\w+\s*(?:<-|=)', clean):
            continue
        # Extract the variable name from the LHS
        lhs_m = re.match(r'^\s*(\w+)\s*(?:<-|=)', clean)
        if not lhs_m:
            continue
        varname = lhs_m.group(1)
        if varname in vars_map:
            continue  # already fully resolved
        # Apply partial preprocessing to the full line
        partial_clean, was_partial = _preprocess_helpers_partial(clean, vars_map)
        if not was_partial:
            continue
        # Expand fully-known vars
        for _var, _val in vars_map.items():
            partial_clean = re.sub(rf'\b{re.escape(_var)}\b', f'"{_val}"', partial_clean)
        # Now check if the assignment resolved to a quoted string
        m_qa = _VAR_ASSIGN_QUOTED_RE.match(partial_clean)
        if m_qa and m_qa.group(1) == varname:
            path = m_qa.group(2) if m_qa.group(2) is not None else m_qa.group(3)
            if path and ('{' in path or '.' in path or '/' in path):
                partial_vars_map[varname] = path

    events: list[ParsedEvent] = []
    child_scripts: list[str] = []
    global_warnings: list[Diagnostic] = []
    excluded_references: list[Diagnostic] = []

    seen_paths: set[tuple[str, str]] = set()

    def _add_event(line_no: int, command: str, raw_path: str, is_write: bool) -> None:
        if _is_external(raw_path):
            global_warnings.append(Diagnostic(
                level='info',
                code='external_reference',
                message=f'External reference skipped in {rel_script}:{line_no}: {raw_path}',
                payload={'script': rel_script, 'path': raw_path},
            ))
            return
        # Guard: a raw_path that is a bare directory reference (e.g. ".", "./",
        # or any path ending with "/" or "\") has no filename component and
        # would produce a spurious directory node.  Discard silently.
        stripped_rp = raw_path.rstrip('/\\')
        if stripped_rp in ('', '.', '..') or raw_path.endswith('/') or raw_path.endswith('\\'):
            return
        resolved_path = raw_path
        if '..' in raw_path and not Path(raw_path).is_absolute():
            resolved_path = str((r_file.parent / raw_path).resolve())
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
        candidate = r_file.parent / raw_path
        if candidate.exists():
            raw_path = str(candidate.relative_to(project_root)).replace('\\', '/')
        norm, _ = to_project_relative(project_root, Path(raw_path), normalization)
        norm = normalize_token(norm)
        if norm not in child_scripts:
            child_scripts.append(norm)

    def _add_event_partial(line_no: int, command: str, placeholder_path: str, dynamic_pattern: str) -> None:
        """Emit a write event with partial resolution (placeholder node).

        The placeholder_path may contain {varname} tokens and may be an absolute path
        prefixed with the project root. We strip the project root prefix if present so
        the resulting node ID is project-relative.
        """
        # Strip project root prefix if the path starts with it (handles absolute partial paths)
        proj_root_str = str(project_root).replace('\\', '/').rstrip('/')
        norm_ph = placeholder_path.replace('\\', '/').rstrip('/')
        if norm_ph.startswith(proj_root_str + '/'):
            norm_ph = norm_ph[len(proj_root_str) + 1:]
        # Resolve any '..' segments in the non-placeholder portion
        # We can't use Path().resolve() because of {varname} tokens, so handle manually
        parts = norm_ph.split('/')
        cleaned: list[str] = []
        for part in parts:
            if part == '..':
                if cleaned:
                    cleaned.pop()
            elif part and part != '.':
                cleaned.append(part)
        norm = normalize_token('/'.join(cleaned))
        key = (command, norm)
        if key in seen_paths:
            return
        seen_paths.add(key)
        events.append(ParsedEvent(
            script=rel_script,
            line=line_no,
            command=command,
            raw_path=placeholder_path,
            normalized_paths=[norm],
            was_absolute=False,
            resolution_status='partial',
            dynamic_pattern=dynamic_pattern,
        ))

    all_write_patterns = _WRITES_DATA_THEN_PATH + _WRITES_KEYWORD

    for line_no, raw_line in enumerate(joined_lines, start=1):
        line = _strip_comment(raw_line)

        # --- Script calls ---
        for pattern in (_SOURCE_RE, _SYS_SOURCE_RE):
            m = pattern.search(line)
            if m:
                raw = m.group(1) or m.group(2)
                if raw:
                    _add_child(raw)

        # Save the original stripped line before path-helper preprocessing
        # so we can try partial resolution later if the full pass misses.
        original_line = line

        # --- Preprocess path helpers (inline replacement) ---
        line, _ = _preprocess_helpers(line, vars_map)

        # --- Expand bare variable names to quoted values for pattern matching ---
        for _var, _val in vars_map.items():
            line = re.sub(rf'\b{re.escape(_var)}\b', f'"{_val}"', line)

        # --- list.files: directory-scan wildcard read ---
        # Recognises list.files(path, ...) and emits a wildcard read edge.
        # If a pattern= argument containing an escaped extension (e.g. "\\.csv$")
        # is found on the same line, we use that extension; otherwise emit /**/*.
        _lf_m = _LIST_FILES_RE.search(line)
        if _lf_m:
            _lf_args = _lf_m.group(1).strip()
            # The first positional argument is either a quoted string or a variable
            _lf_folder: str | None = None
            _first_arg_m = _QUOTED_RE.search(_lf_args)
            if _first_arg_m:
                _lf_folder = _first_arg_m.group(1) or _first_arg_m.group(2)
            else:
                # Try resolving the first identifier token as a variable
                _first_token = re.match(r'(\w+)', _lf_args)
                if _first_token:
                    _lf_folder = vars_map.get(_first_token.group(1))
            if _lf_folder:
                # Try to infer suffix from pattern= argument on same line
                _lf_suffix: str | None = None
                _lf_pat_m = _LIST_FILES_PATTERN_RE.search(line)
                if _lf_pat_m:
                    _lf_pat_str = _lf_pat_m.group(1) or _lf_pat_m.group(2)
                    _lf_ext_m = _EXT_FROM_PATTERN_RE.search(_lf_pat_str)
                    if _lf_ext_m:
                        _lf_suffix = '.' + _lf_ext_m.group(1)
                _wildcard_node_lf = _lf_folder.rstrip('/') + ('/**/*' + _lf_suffix if _lf_suffix else '/**/*')
                _add_event(line_no, 'list_files', _wildcard_node_lf, is_write=False)

        # --- Read patterns ---
        matched_read = False
        for command, pattern in _READS_FIRST_ARG:
            raw = _try_match(pattern, line, vars_map)
            if raw is not None:
                _add_event(line_no, command, raw, is_write=False)
                matched_read = True
                break

        if not matched_read:
            # readRDS(file="path")
            raw = _try_match(_READRDS_KW_RE, line, vars_map)
            if raw is not None:
                _add_event(line_no, 'readRDS', raw, is_write=False)

        # --- Write patterns ---
        matched_write = False
        for command, pattern in all_write_patterns:
            raw = _try_match(pattern, line, vars_map)
            if raw is not None:
                _add_event(line_no, command, raw, is_write=True)
                matched_write = True
                break

        # --- Kwarg heuristic: any function call with a path-kwarg name ---
        # Covers user-defined functions at call sites (do NOT enter the function body).
        # Only runs when no known write pattern already fired.
        if not matched_write:
            for kw_m in _KWARG_PATH_RE.finditer(line):
                raw_kw = kw_m.group(2) if kw_m.group(2) is not None else kw_m.group(3)
                if raw_kw and ('.' in raw_kw or '/' in raw_kw):
                    _add_event(line_no, 'inferred_kwarg', raw_kw, is_write=True)
                    matched_write = True
                    # continue to find all kwarg paths on this line
            # Don't break after first — allow all kwarg matches per line

        # --- Partial write pass: if no full match, try partial path resolution ---
        # This handles cases like ggsave(filename = file.path(dir, paste0("plot_", var, ".png")))
        # where a loop variable prevents full resolution.
        if not matched_write:
            partial_line, was_partial = _preprocess_helpers_partial(original_line, vars_map)
            # Also expand partial vars (e.g. out_file <- file.path(..., loop_var, ...))
            combined_partial = False
            for _var, _val in partial_vars_map.items():
                if re.search(rf'\b{re.escape(_var)}\b', partial_line):
                    partial_line = re.sub(rf'\b{re.escape(_var)}\b', f'"{_val}"', partial_line)
                    combined_partial = True
            if was_partial or combined_partial:
                # Expand known (fully-resolved) vars in the partially-resolved line
                for _var, _val in vars_map.items():
                    partial_line = re.sub(rf'\b{re.escape(_var)}\b', f'"{_val}"', partial_line)
                for command, pattern in all_write_patterns:
                    raw = _try_match(pattern, partial_line, vars_map)
                    if raw is not None:
                        # raw is the partially-resolved placeholder path
                        _add_event_partial(line_no, command, raw, dynamic_pattern=raw)
                        break

    return ScriptParseResult(
        events=events,
        child_scripts=child_scripts,
        global_warnings=global_warnings,
        excluded_references=excluded_references,
        globals_map=vars_map,
    )
