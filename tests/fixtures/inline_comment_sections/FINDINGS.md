# Inline comment false positives — findings

## generate_graphs.py — false positives

| Line | Level | Title | Is inside function body? |
|------|-------|-------|------------------------|
| 24 | 1 | Compute statistics | Yes (get_boxplot_2) |
| 28 | 1 | Draw box | Yes (get_boxplot_2) |
| 34 | 1 | testing | No (module level — from `## testing`) |
| 42 | 1 | Modern Nord-Style Colours | Yes (plot_trajectories) |
| 45 | 1 | Price trajectories | Yes (plot_trajectories) |
| 49 | 1 | Quantity effect curves | Yes (plot_trajectories) |
| 53 | 1 | Quantity effect areas | Yes (plot_trajectories) |
| 56 | 1 | Formatting | Yes (plot_trajectories) |

Total false positives: 8

Notes:
- `# --- Compute statistics ---` also appears at L11 (get_boxplot), but deduplicated by
  `_dedup_exact_titles` — only the last occurrence (L24) is kept.
- `# --- Draw box ---` also appears at L16 (get_boxplot), but deduplicated — only L28 kept.
- So the raw pattern matches 10 lines; after dedup the output shows 8 entries.

## clean_script.py — correct results (control)

| Line | Level | Title |
|------|-------|-------|
| 1 | 1 | 1. Load data |
| 6 | 1 | 2. Clean |
| 11 | 1 | 3. Save |

The `###`-prefixed section headers are correctly detected (3 entries, no false positives).

## Root cause confirmed

- Pattern matched by extractor for `# --- Title ---` lines:
  Python pattern #5 (index 4 in `_PY_PATTERNS`):
  `r"^\s*#\s*[-=*]{2,}\s*([A-Z][^#]{3,}?)\s*[-=*]{0,}\s*$"`
  This matches any single-`#` comment where the title is flanked by 2+ decoration chars
  (`-`, `=`, `*`) and the extracted title starts with an uppercase letter.
  This is intended for headings like `# ===== Section =====` but also fires on
  indented inline comments like `    # --- Compute statistics ---` because the
  regex does not anchor on leading whitespace before the `#`.

- Pattern matched for `## testing`:
  Python pattern #3 (index 2 in `_PY_PATTERNS`):
  `r"^\s*#{2,}(?:\s+)(?!\[\d)(.+?)\s*#{0,}\s*$"`
  Any multi-hash comment (`##`, `###`, etc.) is treated as a section header.
  `## testing` has two hashes, so it qualifies.

- Indentation not checked: Yes — all `# --- ... ---` false positives are indented inside
  function bodies (4+ spaces), but the regex `^\s*#\s*` allows arbitrary leading whitespace,
  so indented inline comments are matched exactly as if they were top-level headers.

- The `## testing` line: PICKED UP — appears in output as L34, level 1, title "testing".
  It is at module level (not inside a function), so it is a borderline case — it is not a
  `# ---` false positive, but `## testing` is a commented-out code note, not a section
  header either.

- Extractor file and line number where the pattern is defined:
  `src/data_pipeline_flow/parser/section_extract.py`, line 449
  (`_PY_PATTERNS` list, entry at index 4):
  `(re.compile(r"^\s*#\s*[-=*]{2,}\s*([A-Z][^#]{3,}?)\s*[-=*]{0,}\s*$"), False)`
