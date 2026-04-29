# os.walk + open(variable, "w") — findings

## os.walk pattern
- Read edge present? No
- If Yes: node ID = N/A
- Expected: read edge to `../results/**` (or similar wildcard for directory traversal)
- Note: `os.walk(BASE_DIR)` produces no edge at all. `BASE_DIR` is computed via
  `os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")`.
  The `os.path.join` resolution strips the absolute prefix and cannot reduce to a
  project-relative path (the `../results` folder does not exist inside the fixture),
  so no edge is emitted. Additionally, `os.walk` itself is not in any read pattern
  in `python_extract.py`; even if `BASE_DIR` resolved cleanly it would require a
  dedicated `os.walk` pattern to produce a read edge.

## open(VARIABLE, "w") pattern
- Write edge for completeness_report.txt? Yes
- Spurious read edge also present? Yes (NH-13 double-emit confirmed)
- Cycle diagnostic present? Yes

### Explanation of double-emit
After variable expansion (lines 1197–1211 of python_extract.py), the line
`with open(OUTPUT_FILE, "w") as out:` becomes
`with open("completeness_report.txt", "w") as out:`.

1. **Spurious read edge**: The `open_read` regex (line 297) has an optional mode
   group `(?:,\s*(?:..."r[bt]?"...))?`. The `"w"` mode is not excluded — it simply
   fails the optional group, which is then skipped. The regex still captures
   `completeness_report.txt` and emits `open_read` → spurious read edge.

2. **Correct write edge**: The `open_write` regex (line 364) also matches the same
   expanded line with mode `"w"` and emits a correct write edge.

Both edges are emitted in the same pass, causing the cycle.

## edges.csv (full)
```
source,target,command,kind
completeness_report.txt,analysis/check_completeness.py,open_read,generated_artifact
analysis/check_completeness.py,completeness_report.txt,open_write,deliverable
```

## Diagnostics observed
| code | level | message |
|------|-------|---------|
| excluded_files | info | Excluded 1 files during discovery. |
| project_scan | info | Project discovery completed. |
| missing_referenced_file | warning | Referenced path does not exist in project tree: completeness_report.txt |
| cycle_detected | warning | Cycle detected: analysis/check_completeness.py -> completeness_report.txt -> analysis/check_completeness.py |
| excluded_path_inventory | info | 1 excluded paths recorded in this run. |

## Root cause confirmed
- `os.walk` is not in any read pattern in `python_extract.py`. No pattern matches
  `os.walk(...)` as a file-read event. Search for `os.walk` in
  `src/data_pipeline_flow/parser/python_extract.py` returns no matches.
- `open()` variable tracking: the `"w"` mode IS detected (write edge emitted
  correctly via `open_write` pattern after variable expansion). However the
  `open_read` pattern also fires on the same line because its mode group is
  optional and does not explicitly exclude write modes (`"w"`, `"a"`, `"wb"`, etc.).
  This is the double-emit bug tracked as NH-13.
