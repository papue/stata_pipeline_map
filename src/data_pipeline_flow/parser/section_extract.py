"""section_extract — detect and emit logical section headers from script files.

=============================================================================
PATTERN SPECIFICATION
=============================================================================

Overview
--------
This module scans a single script file (.do / .py / .R / .r) line-by-line and
returns a list of detected section header records.  Only lines that carry a
meaningful title are emitted; pure decorator lines (lines whose entire content
is repetitions of a decoration character) are silently skipped.

The result is consumed by the CLI command ``extract-sections`` which writes a
``sections.json`` index keyed by stable project-relative node IDs.

=============================================================================
STATA (.do files)
=============================================================================

All Stata comment syntaxes are considered: single-star comments (``*``),
double-slash comments (``//``), and block comments (``/* … */``).

--- Family 1: Decorator-only lines — SKIP ---

A line whose non-whitespace content after the leading ``*`` (or ``//``) consists
entirely of repeated decoration characters is a pure separator and is NOT
emitted.  Recognised decoration characters: ``*``, ``-``, ``_``, ``=``, ``~``.

Examples (all skipped):
    *************************************
    *------------------------------------
    *____________________________________
    *====================================
    *~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    // ====================================
    //-------------------------------------

Formal rule:  after stripping the leading comment token and surrounding
whitespace, if the remaining string matches ``[*\\-_=~]{2,}`` the line is a
decorator and is skipped.

--- Family 2: Sandwiched header ---

A title line that is immediately preceded AND followed by a decorator-only line
(see Family 1) is a "sandwiched" header.  The decorator lines themselves are
not emitted; only the inner title line is emitted.

Example (three consecutive lines in the file):

    ****
    * 1. Prepare data
    ****

Emitted record:  line = line number of the inner title line,
                 title = "1. Prepare data",  level inferred from title text.

Note: the lookahead/lookbehind is handled during post-processing of the line
stream; the decorator lines must directly adjoin the title line (no blank lines
between them) for this family to match.

--- Family 3: Plain numbered (single-star or double-slash) ---

    * 1. Prepare sales data
    * 2. Run regressions
    // 1. Prepare data

Pattern (applied after stripping ``*`` or ``//`` and trimming whitespace):
    ``^(\\d+)\\.\\s+\\S.*``  → level 1

--- Family 4: Sub-numbered ---

    * 1.2 Filter outliers
    // 1.2 Merge datasets

Pattern:
    ``^(\\d+)\\.(\\d+)\\s+\\S.*``  → level 2

--- Family 5: Deep numbered ---

    * 1.2.3 Remove duplicates

Pattern:
    ``^(\\d+)\\.(\\d+)\\.(\\d+)\\s+\\S.*``  → level 3

--- Family 6: Letter-numbered (mixed alpha-numeric) ---

    * 1.A Robustness checks
    * A.1 Appendix tables
    * A.1.2 Sub-appendix

Patterns:
    ``^(\\d+)\\.([A-Za-z])\\s+\\S.*``         → level 2
    ``^([A-Za-z])\\.(\\d+)\\s+\\S.*``         → level 2
    ``^([A-Za-z])\\.(\\d+)\\.(\\d+)\\s+\\S.*``  → level 3

--- Family 7: Inline decorated ---

Lines where the title is flanked by decoration characters on both sides:

    *** 1. Title ***
    *--- Section ---*
    //=== Section ===//

Rule: after stripping the comment token, if the line matches
``^[*\\-_=~]+\\s+(.+?)\\s+[*\\-_=~]+$`` extract the inner text as the title.
The title must contain at least one word character; if the extracted text is
itself a pure decoration string, the line is skipped (decorator-only).

--- Family 8: Double-slash plain ---

    // 1. Prepare data
    // Setup

Treated identically to single-star comment families above.  After stripping
``//`` and trimming, apply the same numbered-title and plain-title rules.

--- Family 9: Block comment header ---

A single-line block comment whose content (after stripping ``/*`` and ``*/``)
looks like a decorated or numbered title:

    /* ===== Section ===== */
    /* 1. Introduction */

Multi-line block comments are NOT parsed for section headers in this version.

=============================================================================
PYTHON (.py files)
=============================================================================

--- Family 1: Multi-hash plain ---

Lines beginning with two or more ``#`` characters followed by a space and a
non-empty, non-decorator title.

    ## Title               → level 1
    ### Title              → level 1  (hash depth is ignored; level comes from
    #### Title               numbering prefix, not hash count)

If the title after the hashes is a numbered prefix (e.g. ``## 1.2 Subsection``)
the level is inferred from the number rather than the hash depth.

Pure decorator lines (``##====``, ``##----``) are skipped per the same
decorator-only rule as Stata.

--- Family 2: Decorated single-hash ---

    # ===== Title =====
    # ----- Title -----
    # ***** Title *****

Rule: ``^#\\s+[=*\\\\-]{2,}\\s+(.+?)\\s+[=*\\\\-]{2,}\\s*$`` — extract inner title.
If the extracted text is a pure decorator string, skip.

--- Family 3: Numbered with decoration ---

    # ---- 1. Title ----
    # ==== 1.2 Subsection ====

Covered by the combination of Family 2 (extract inner text) and the numbered
level-inference rules applied to the extracted text.

--- Family 4: Cell marker (Spyder / VSCode) ---

    # %% 1. Load data
    # %% Section title
    # %%

The ``# %%`` prefix is the standard Spyder/VSCode cell marker.  The text after
``# %%`` (trimmed) is the title.  If no text follows (bare ``# %%``) the cell
is emitted with title ``"(untitled cell)"`` so that cell boundaries are still
visible in the index.

Level: always 1, regardless of any numbering in the title.

--- Family 5: Notebook cell marker ---

    # In[1]:
    # In[42]:
    # In[ ]:

Emitted with title ``"Cell N"`` (where N is the bracket content, e.g. ``"Cell 1"``
or ``"Cell  "`` for an unsaved cell).  Level: always 1.

--- Family 6: Hash-star mix ---

    # *** Section ***
    # *** 1. Analysis ***

Treated as a decorated line; apply the same flanking-decoration rule as
Family 7 in Stata.

--- Family 7: Decorator-only ``#****`` — SKIP ---

    #****
    #----
    # =============================

A Python line whose content after ``#`` (trimmed) is a pure decoration string
is skipped.

=============================================================================
R (.R and .r files)
=============================================================================

--- Family 1: RStudio section marker (trailing ``----``) ---

RStudio treats any comment line ending with four or more dashes as a foldable
section header.

    ## 1. Load data ----
    # Prepare data ----
    ### Subsection ----

Rule: ``^#+\\s*(.+?)\\s*-{4,}\\s*$`` — extract the title (stripping trailing
dashes).  Level inferred from title text (numbered prefix rule).

--- Family 2: RStudio section marker (trailing ``####``) ---

    # Prepare data ####
    ## 1.2 Step ####

Rule: ``^#+\\s*(.+?)\\s*#{4,}\\s*$`` — extract the title.

--- Family 3: RStudio section marker (trailing ``====``) ---

    # Filter data ====
    ## 2. Merge ====

Rule: ``^#+\\s*(.+?)\\s*={4,}\\s*$`` — extract the title.

--- Family 4: Decorated (symmetric) ---

    # ==== Title ====
    # ---- Title ----

Same rule as Python Family 2.  Title extracted from between the decoration
sequences.

--- Family 5: Multi-hash numbered ---

    ### 1.2 Subsection ###
    ## 2. Section ##

Rule: ``^#+\\s*(.+?)\\s*#+\\s*$`` — extract title; must not be a pure decorator
after extraction.  Level inferred from numbering prefix of extracted title.

=============================================================================
LEVEL INFERENCE RULES (all languages)
=============================================================================

Applied to the *extracted* title text (after all decoration has been stripped):

    Pattern                      Level
    --------------------------   -----
    ``^\\d+\\. ``                  1     e.g. "1. Prepare data"
    ``^[A-Za-z]\\. ``             1     e.g. "A. Appendix"
    ``^\\d+\\.\\d+ ``               2     e.g. "1.2 Filter outliers"
    ``^[A-Za-z]\\.\\d+ ``          2     e.g. "A.1 Appendix tables"
    ``^\\d+\\.[A-Za-z] ``          2     e.g. "1.A Robustness checks"
    ``^\\d+\\.\\d+\\.\\d+ ``          3     e.g. "1.2.3 Remove duplicates"
    ``^[A-Za-z]\\.\\d+\\.\\d+ ``     3     e.g. "A.1.2 Sub-appendix"
    (no numbering prefix)        1     plain title, default level
    Cell markers (# %%, In[N]:)  1     always, regardless of title text

Patterns are tested in the order listed; the first match wins.

=============================================================================
OUTPUT SCHEMA
=============================================================================

``extract_sections`` returns a list of dicts, one per detected section header,
in file order:

    [
        {
            "line":  <int>,   # 1-based line number in the source file
            "level": <int>,   # 1 | 2 | 3
            "title": <str>    # cleaned title text (decoration stripped,
                              # leading/trailing whitespace stripped)
        },
        ...
    ]

Files with zero detected headers return an empty list ``[]``.

The CLI command ``extract-sections`` collects these per-file lists and writes
``sections.json``, keyed by stable project-relative node IDs (forward-slash
separators, project root stripped):

    {
        "scripts/01_prepare.do": [
            {"line": 12, "level": 1, "title": "1. Prepare sales data"},
            {"line": 45, "level": 2, "title": "1.2 Filter outliers"}
        ],
        "scripts/analyze.py": [
            {"line": 1,  "level": 1, "title": "Load data"}
        ]
    }

Files with zero detected sections are omitted from ``sections.json`` entirely.

=============================================================================
EDGE CASES AND NOTES
=============================================================================

- Encoding: files are read as UTF-8 with ``errors="replace"`` so that
  non-UTF-8 bytes do not abort extraction.
- Line endings: ``\\r\\n`` (Windows) and ``\\r`` (old Mac) are normalised to
  ``\\n`` before pattern matching.
- Tabs: leading tabs in Stata ``*`` comments are treated identically to spaces.
- Empty title guard: after stripping decoration, if the remaining title is
  empty or consists only of whitespace, the line is skipped (not emitted).
- Duplicate consecutive titles: consecutive identical titles at the same line
  are not de-duplicated; the caller may post-process as needed.
- Multi-line block comments (Stata ``/* … */`` spanning multiple lines) are
  not scanned for section headers in this version; only single-line block
  comment patterns are matched.
- Stata ``///`` line continuation is not resolved before matching; each
  physical line is matched independently.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Section:
    line: int    # 1-based line number
    level: int   # 1 = top-level, 2 = sub, 3 = sub-sub
    title: str   # cleaned title text, no decoration chars


# ---------------------------------------------------------------------------
# Language detection
# ---------------------------------------------------------------------------

def _detect_language(file_path: Path) -> str:
    """Return 'stata' | 'python' | 'r' | 'unknown' from file extension."""
    ext = file_path.suffix.lower()
    return {".do": "stata", ".py": "python", ".r": "r"}.get(ext, "unknown")


# ---------------------------------------------------------------------------
# Decorator-line detection (consumed but NOT emitted)
# ---------------------------------------------------------------------------

# Characters that form pure decoration sequences
_DECO_CHARS = r"[\*\-_=~.]"

_STATA_DECO_RE = re.compile(r"^\s*\*" + _DECO_CHARS + r"{2,}\s*$")
_STATA_DECO_SLASH_RE = re.compile(r"^\s*#{1,}" + _DECO_CHARS + r"{3,}\s*$")  # fallback
_PY_R_DECO_RE = re.compile(r"^\s*#{1,}" + _DECO_CHARS + r"{3,}\s*$")


def _is_decorator(line: str, lang: str) -> bool:
    """Return True if *line* is a pure decorator line (should be consumed but not emitted)."""
    if lang == "stata":
        # Single-star decorator: *----  *====  *~~~~  *....
        if re.match(r"^\s*\*" + _DECO_CHARS + r"{2,}\s*$", line):
            return True
        # All-star line: **** (no space, no text)
        if re.match(r"^\s*\*{3,}\s*$", line):
            return True
        # Double-slash decorator: //---  //====
        if re.match(r"^\s*//\s*" + _DECO_CHARS + r"{3,}\s*$", line):
            return True
        return False
    else:  # python, r
        # ##----  # ====  #**** etc.
        if re.match(r"^\s*#{1,}\s*" + _DECO_CHARS + r"{3,}\s*$", line):
            return True
        return False


# ---------------------------------------------------------------------------
# Title cleaning
# ---------------------------------------------------------------------------

_CLEAN_RE = re.compile(r'^[*\-=_~#\s]+|[*\-=_~#\s]+$')
_PUNCT_ONLY_RE = re.compile(r'^[\W_]+$')  # only non-word chars


def _clean_title(raw: str) -> str | None:
    """Strip leading/trailing decoration from *raw*.  Return None if empty or punctuation-only."""
    title = _CLEAN_RE.sub("", raw).strip()
    if not title:
        return None
    if _PUNCT_ONLY_RE.match(title):
        return None
    return title


# ---------------------------------------------------------------------------
# Level inference
# ---------------------------------------------------------------------------

def _infer_level(title: str) -> int:
    """Infer section depth (1-3) from numbering prefix of *title*."""
    m = re.match(r'^([A-Za-z\d]+(?:\.[A-Za-z\d]+)*)\s*\.?\s', title)
    if not m:
        return 1
    parts = m.group(1).split('.')
    return min(len(parts), 3)


# ---------------------------------------------------------------------------
# Per-language header parsers
# ---------------------------------------------------------------------------

# --- Stata patterns (ordered; first match wins) ---
_STATA_PATTERNS: list[tuple[re.Pattern, bool]] = [
    # 1. numbered, optional trailing stars: * 1. Title *  or  * 1.2 Title
    (re.compile(r"^\s*\*{1,}\s*(\d[\d.A-Za-z]*\.?\s+.+?)\s*\*{0,}\s*$"), False),
    # 1b. inline decorated numbered: * -- 1. Title --  or  * === 1.2 Sub ===
    (re.compile(r"^\s*\*+\s*[-=_~]{2,}\s*(\d[\d.A-Za-z]*\.?\s+.+?)\s*[-=_~]{0,}\s*$"), False),
    # 2. double-slash numbered: // 1. Title
    (re.compile(r"^\s*//\s*(\d[\d.A-Za-z]*\.?\s+.+?)\s*$"), False),
    # 3. block comment decorated: /* ===== Title ===== */
    (re.compile(r"^\s*/\*\s*[=\-*]{2,}\s*(.+?)\s*[=\-*]{2,}\s*\*/\s*$"), False),
    # 4. title-case unnumbered decorated: ** Some Title **
    (re.compile(r"^\s*\*{2,}\s*([A-Z][^*]{3,}?)\s*\*{0,}\s*$"), False),
]

# --- Python patterns (ordered; first match wins) ---
_PY_PATTERNS = [
    # 1. cell marker: # %% title  (must have whitespace after %% to distinguish from IPython magics)
    #    IPython magics look like # %%time (no space); cell markers are # %% or # %% <title>
    (re.compile(r"^\s*#\s*%%(\s+(.+?))?\s*$"), "cell"),
    # 2. notebook cell: # In[N]:
    (re.compile(r"^\s*#\s*In\[(\d*)\]:"), "notebook"),
    # 3. multi-hash: ## Title  or  ### Title
    #    Require whitespace after ## and reject [N] prefix (R console output, e.g. ## [1] 0.234)
    (re.compile(r"^\s*#{2,}(?:\s+)(?!\[\d)(.+?)\s*#{0,}\s*$"), False),
    # 4. decorated numbered: # ---- 1. Title ----
    (re.compile(r"^\s*#\s*[-=*]{2,}\s*(\d[\d.A-Za-z]*\.?\s+.+?)\s*[-=*]{0,}\s*$"), False),
    # 5. decorated unnumbered title-case: # ===== Section =====
    #    Require no leading whitespace (column 0) so indented inline comments like
    #    `    # --- Compute statistics ---` inside function bodies are not matched.
    (re.compile(r"^#\s*[-=*]{2,}\s*([A-Z][^#]{3,}?)\s*[-=*]{0,}\s*$"), False),
]

# --- R patterns (ordered; first match wins) ---
_R_PATTERNS = [
    # 1. RStudio trailing marker (----, ####, ====): # Title ----
    (re.compile(r"^\s*#{1,}\s*(.+?)\s*[-=#]{4,}\s*$"), False),
    # 2. multi-hash: ## Title  or  ### Title
    #    Require whitespace after ## and reject [N] prefix (R console output, e.g. ## [1] TRUE)
    (re.compile(r"^\s*#{2,}(?:\s+)(?!\[\d)(.+?)\s*#{0,}\s*$"), False),
    # 3. decorated: # ==== Title ==== or # ---- Title ----
    #    Require no leading whitespace (column 0) so indented inline comments like
    #    `  # --- internal step ---` inside R function bodies are not matched.
    (re.compile(r"^#\s*[-=*]{2,}\s*(.+?)\s*[-=*]{0,}\s*$"), False),
]


def _parse_header_stata(line: str, lineno: int) -> Section | None:
    """Try each Stata pattern in order; return Section on first match."""
    for pat, _ in _STATA_PATTERNS:
        m = pat.match(line)
        if m:
            raw = m.group(1)
            title = _clean_title(raw)
            if title:
                return Section(line=lineno, level=_infer_level(title), title=title)
    return None


def _parse_header_python(line: str, lineno: int) -> Section | None:
    """Try each Python pattern in order; return Section on first match."""
    for pat, special in _PY_PATTERNS:
        m = pat.match(line)
        if not m:
            continue
        if special == "cell":
            # group(2) is the title text (group(1) is the leading whitespace+title)
            raw = (m.group(2) or "").strip()
            title = raw if raw else "(untitled cell)"
            return Section(line=lineno, level=1, title=title)
        elif special == "notebook":
            n = m.group(1)
            title = f"In[{n}]:"
            return Section(line=lineno, level=1, title=title)
        else:
            raw = m.group(1)
            title = _clean_title(raw)
            if title:
                return Section(line=lineno, level=_infer_level(title), title=title)
    return None


def _parse_header_r(line: str, lineno: int) -> Section | None:
    """Try each R pattern in order; return Section on first match."""
    for pat, _ in _R_PATTERNS:
        m = pat.match(line)
        if m:
            raw = m.group(1)
            title = _clean_title(raw)
            if title:
                return Section(line=lineno, level=_infer_level(title), title=title)
    return None


def _parse_header(line: str, lang: str, lineno: int) -> Section | None:
    """Dispatch to per-language header parser."""
    if lang == "stata":
        return _parse_header_stata(line, lineno)
    elif lang == "python":
        return _parse_header_python(line, lineno)
    elif lang == "r":
        return _parse_header_r(line, lineno)
    return None


# ---------------------------------------------------------------------------
# TOC-block suppression
# ---------------------------------------------------------------------------

_TOC_KEYWORDS = ("table of contents", "contents", " toc")


def _detect_toc_end_line(lines: list[str], lang: str) -> int:
    """Option A: scan raw file lines for a TOC block; return the last line number
    of the block (1-based), or 0 if no TOC block is found.

    A TOC block is detected when ALL of the following hold:

    1. There are 3+ consecutive header-marker lines within the first 30 lines.
       - Python/R:  lines starting with ``##`` or more hashes (``###``, etc.)
       - Stata:     lines starting with ``*`` or ``//`` that are not pure
                    decorator lines (handled by checking the stripped text)
    2. At least one line in the cluster contains a TOC keyword (case-insensitive):
       "table of contents", "contents", or " toc".
    3. The cluster starts within line 30 of the file.
    """
    # Build per-language "looks like a header comment" detector
    if lang == "python":
        def _is_header_comment(raw: str) -> bool:
            return bool(re.match(r"^\s*#{2,}\s*\S", raw))
    elif lang == "r":
        def _is_header_comment(raw: str) -> bool:
            return bool(re.match(r"^\s*#{1,}\s*\S", raw))
    else:  # stata
        def _is_header_comment(raw: str) -> bool:
            stripped = raw.strip()
            if re.match(r"^\*\s*\S", stripped):
                return True
            if re.match(r"^//\s*\S", stripped):
                return True
            return False

    # Find runs of consecutive header-comment lines within the first 30 lines
    run_start = -1
    run_lines: list[tuple[int, str]] = []  # (1-based lineno, stripped text)

    for i, raw in enumerate(lines[:30], start=1):
        if _is_header_comment(raw):
            if run_start < 0:
                run_start = i
            run_lines.append((i, raw.strip()))
        else:
            if len(run_lines) >= 3:
                # We have a qualifying run — check for TOC keyword
                combined = " ".join(t for _, t in run_lines).lower()
                if any(kw in combined for kw in _TOC_KEYWORDS):
                    return run_lines[-1][0]
            # Reset run (allow up to 1 blank line gap)
            if raw.strip():
                run_start = -1
                run_lines = []

    # Check run that extends to end of first-30-lines window
    if len(run_lines) >= 3:
        combined = " ".join(t for _, t in run_lines).lower()
        if any(kw in combined for kw in _TOC_KEYWORDS):
            return run_lines[-1][0]

    return 0


def _dedup_exact_titles(sections: list[Section]) -> list[Section]:
    """Option B (secondary): for exact-title duplicates keep the last occurrence.

    This is applied *after* Option A to handle any exact duplicates that escaped
    TOC-block detection (e.g. single-entry TOC, or a non-detected TOC block).
    Sections with unique titles are unaffected.
    """
    if not sections:
        return sections

    from collections import Counter
    title_counts = Counter(s.title.strip() for s in sections)
    duplicate_titles = {t for t, n in title_counts.items() if n > 1}
    if not duplicate_titles:
        return sections

    # For each duplicated title keep only the last (highest line number)
    last_line_for: dict[str, int] = {}
    for s in sections:
        t = s.title.strip()
        if t in duplicate_titles:
            last_line_for[t] = max(last_line_for.get(t, 0), s.line)

    result = []
    for s in sections:
        t = s.title.strip()
        if t in duplicate_titles and s.line != last_line_for[t]:
            continue  # earlier duplicate — drop it
        result.append(s)
    return result


def _suppress_toc_block(
    sections: list[Section],
    lines: list[str],
    lang: str,
) -> list[Section]:
    """Apply Option A (TOC block detection) then Option B (exact-title dedup).

    Option A detects a dense cluster of header-comment lines near the top of the
    file that contains a TOC keyword, and suppresses every parsed section whose
    line number falls within that block.

    Option B deduplicates any remaining exact-title duplicates by keeping the
    last occurrence (highest line number).
    """
    if not sections:
        return sections

    toc_end = _detect_toc_end_line(lines, lang)
    if toc_end > 0:
        sections = [s for s in sections if s.line > toc_end]

    return _dedup_exact_titles(sections)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_sections(file_path: Path, language: str = "auto") -> list[Section]:
    """Extract section headers from a script file.

    Parameters
    ----------
    file_path:
        Path to the script file to scan (.do / .py / .R / .r).
    language:
        One of ``"stata"`` | ``"python"`` | ``"r"`` | ``"auto"``.
        When ``"auto"`` (default) the language is inferred from the file
        extension.

    Returns
    -------
    list[Section]
        Ordered list of :class:`Section` records.  Returns ``[]`` when the
        file is unreadable, the extension is not recognised, or no headers
        are found.
    """
    try:
        # Resolve language
        lang = language
        if lang == "auto":
            lang = _detect_language(file_path)
        if lang == "unknown":
            return []

        # Read file
        text = Path(file_path).read_text(encoding="utf-8", errors="replace")
        # Normalise line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        lines = text.split("\n")

        sections: list[Section] = []
        decorator_seen = False

        for i, raw_line in enumerate(lines, start=1):
            line = raw_line.rstrip("\n")
            if _is_decorator(line, lang):
                decorator_seen = True
                continue
            section = _parse_header(line, lang, i)
            if section:
                sections.append(section)
            decorator_seen = False  # noqa: F841 (kept for spec compliance)

        return _suppress_toc_block(sections, lines, lang)

    except Exception as e:
        logger.debug("section_extract: skipping %s: %s", file_path, e)
        return []
