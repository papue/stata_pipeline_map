# Spurious open_read edge — findings

## Edge table (from edges.csv)

| from | to | relationship | Expected? |
|------|----|-------------|----------|
| config.txt | analysis/report_writer.py | open_read | Yes — Pattern 4 explicit "r" mode |
| analysis/report_writer.py | processing.log | open_write | Yes — Pattern 2 append "a" mode |
| analysis/report_writer.py | reports/details.txt | open_write | Yes — Pattern 3 variable-built path "w" mode |
| analysis/report_writer.py | summary_report.txt | open_write | Yes — Pattern 1 string constant "w" mode |

## Spurious read edges

| Pattern | Path | Read edge emitted? | Write edge emitted? | Both emitted (bug)? |
|---------|------|-------------------|--------------------|--------------------|
| Pattern 1: open(CONSTANT, "w") | summary_report.txt | No | Yes | No — NH-06 fixed |
| Pattern 2: open(CONSTANT, "a") | processing.log | No | Yes | No — NH-06 fixed |
| Pattern 3: open(os.path.join(...), "w") | reports/details.txt | No | Yes | No — NH-06 fixed |
| Pattern 4: open("config.txt", "r") | config.txt | Yes | No | No — correct behaviour |

## Cycle diagnostic

cycle_detected emitted? **No**

No cycle diagnostics were present in the validation report. The 7 diagnostics emitted were:
- excluded_files (info)
- project_scan (info)
- unconsumed_output × 3 (info) — for summary_report.txt, processing.log, reports/details.txt
- missing_referenced_file (warning) — config.txt does not exist in the project tree
- excluded_path_inventory (info)

## Root cause analysis / NH-06 status

**The bug is already resolved by NH-06.**

The fix in `src/data_pipeline_flow/parser/python_extract.py` added a negative lookahead to
the `open_read` pattern (`_FIXED_READ_PATTERNS`) that blocks matching when the mode argument
is `"w"`, `"wb"`, `"a"`, or `"ab"`:

```python
('open_read', re.compile(
    r'\bopen\s*\(\s*(?:[rRbBuU]?"([^"]+)"|[rRbBuU]?\'([^\']+)\')\s*'
    r'(?!,\s*(?:[rRbBuU]?"[wa][bt]?"|[rRbBuU]?\'[wa][bt]?\'))',
    re.I
))
```

This negative lookahead `(?!,\s*(?:[rRbBuU]?"[wa]..."))` prevents `open_read` from firing
when a write or append mode follows the path argument.

Additionally, `_WITH_OPEN_VAR_RB_RE` (used for variable-path opens) only matches explicit
read modes (`"r"`, `"rb"`, `"rt"`), so variable-based writes (Pattern 3) also never emit a
spurious read edge.

## Verification details

- Tool run: `data-pipeline-flow extract-edges --project-root tests/fixtures/spurious_open_read`
- Edges produced: 4 (all correct, zero spurious)
- Cycle diagnostics produced: 0
- Date: 2026-04-28
