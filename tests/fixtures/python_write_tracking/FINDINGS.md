# Task MO-01: Python Write-Side Variable Tracking — Findings

**Date:** 2026-04-25
**Tool version:** data-pipeline-flow (current main)
**Fixture root:** `tests/fixtures/python_write_tracking/`

---

## 1. CLI Commands Run

```bash
data-pipeline-flow extract-edges --project-root tests/fixtures/python_write_tracking --output <edges.csv>
data-pipeline-flow summary      --project-root tests/fixtures/python_write_tracking
data-pipeline-flow snapshot-json --project-root tests/fixtures/python_write_tracking --output <snapshot.json>
```

---

## 2. Edges Detected (Working)

| Source script | Target artifact | Command | Notes |
|---|---|---|---|
| `analysis/export_csv.py` | `output/summary.csv` | `to_csv` | `__file__` + `os.path.join` + `..` resolved correctly |
| `analysis/plot_basic.py` | `analysis/plots/market prices and avg quantity bids.png` | `savefig` | Module-level `plot_name` variable expanded in f-string; path lowercased by normalizer |
| `analysis/plot_chained.py` | `analysis/plots/output_chart.png` | `savefig` | Two-variable chain `_script_dir -> output_dir -> savefig` resolved |
| `analysis/plot_partial.py` | `analysis/plots/{plot_name}.png` | `savefig` | f-string partially resolved (function-scoped `plot_name` not resolvable) — placeholder node created |
| `extract_data.py` | `all_results.parquet` | `to_parquet` | Absolute base `C:\project\results` stripped; only filename retained; `was_absolute=True` warning emitted |
| `write_excel.py` | `output/report.xlsx` | `to_excel` | `__file__` + `os.path.join` resolved; `.xlsx` is a deliverable extension |

---

## 3. Missing Write Edges (Confirmed Failures)

### 3a. Suppressed due to non-deliverable extension

These scripts produce parse events but the graph builder suppresses their edges because:
- `suppress_internal_only_writes = True` (default config)
- the output extension is not in `deliverable_extensions`
  (which includes: `.csv`, `.xlsx`, `.pdf`, `.png`, `.svg`, `.parquet`, `.feather`, `.rds`,
   `.rdata`, `.rda`, `.ster`, `.docx`, `.tex`)
- no external consumer script reads the output

| Source script | Expected target | Command | Extension | Root cause |
|---|---|---|---|---|
| `write_numpy.py` | `output/array.npy` | `np_save` | `.npy` — not deliverable | Parsed correctly; suppressed as non-deliverable unconsumed output |
| `write_numpy.py` | `output/array.txt` | `np_savetxt` | `.txt` — not deliverable | Same; `unconsumed_output` diagnostic emitted |
| `write_json_dump.py` | `output/config.json` | `json_dump` | `.json` — not deliverable | `open_write` fires before `json_dump` due to pattern ordering (see 3b); edge suppressed |
| `write_pickle.py` | `output/model.pkl` | `pickle_dump` | `.pkl` — not deliverable | `open_write` fires before `pickle_dump` due to pattern ordering (see 3b); edge suppressed |

**Diagnostics emitted for numpy outputs (but no edge in CSV):**

```
[info] unconsumed_output: Produced artifact is not consumed downstream: output/array.npy
[info] unconsumed_output: Produced artifact is not consumed downstream: output/array.txt
```

### 3b. Wrong command matched due to write-pattern ordering

For `write_json_dump.py` and `write_pickle.py`, the pattern `open_write` fires before
`json_dump`/`pickle_dump` because of their positions in the combined write-pattern list:

| Pattern | Position in list |
|---|---|
| `open_write` | 21 |
| `pickle_dump` | 22 |
| `json_dump` | 23 |

The parser breaks after the first write match per line (`break  # one write per line (first match)`
at `python_extract.py` line 997). So `open_write` pre-empts the more specific `json_dump` /
`pickle_dump` patterns. The event is recorded as `open_write` rather than `json_dump`/`pickle_dump`.

**Bug:** `json_dump` and `pickle_dump` are more semantically specific patterns that should be
checked before the generic `open_write` pattern.

| Source script | Command actually recorded | Command expected |
|---|---|---|
| `write_json_dump.py` | `open_write` | `json_dump` |
| `write_pickle.py` | `open_write` | `pickle_dump` |

### 3c. Loop-assigned variable — unresolvable at call site

`generate_output.py` writes inside a `for` loop. The variable `filepath` is assigned inside
the loop body via a chain of loop-dependent variables. The parser only resolves top-level,
sequential assignments; variables assigned inside `for`/`while` loops are not tracked.

| Source script | Expected target | Expected command | Root cause |
|---|---|---|---|
| `generate_output.py` | (e.g.) `A/A_result.pdf` | `savefig` | `filepath` set inside `for case in [...]` — loop variable, unresolvable |

No event is emitted; the script node becomes an orphan:

```
[warning] orphan_node: Node has no incoming or outgoing edges: generate_output.py
```

Additionally, the f-string `f"{case}_result.pdf"` does NOT trigger the f-string placeholder
fallback because `.pdf` is missing from `_FSTRING_WITH_EXT_RE`'s extension list. That regex
covers only data formats: `parquet|csv|pkl|pickle|feather|json|xlsx|dta|npy|npz|hdf|h5|orc`
— not image/document output formats such as `.pdf`, `.png` (when used in f-strings).

---

## 4. Partial / Degraded Edges

| Source script | Target (as stored) | Issue |
|---|---|---|
| `analysis/plot_partial.py` | `analysis/plots/{plot_name}.png` | `plot_name` assigned inside a function (`def make_plot`); parser creates a placeholder node with literal `{plot_name}` in the path. Edge is present but target is a non-existent placeholder. |
| `extract_data.py` | `all_results.parquet` | Absolute base path `C:\project\results` stripped — only the filename `all_results.parquet` is retained at project root. Edge present but path is wrong. `was_absolute=True` warning emitted. |
| `analysis/plot_basic.py` | `analysis/plots/market prices and avg quantity bids.png` | Path lowercased by normalizer; actual filename has capital M: `Market prices and avg quantity bids.png`. Resolves on Windows (case-insensitive), would break on Linux. |

---

## 5. Placeholder Nodes Created

| Node ID | Created by | Reason |
|---|---|---|
| `analysis/plots/{plot_name}.png` | `analysis/plot_partial.py` | `plot_name` unresolved (function-scope variable) |
| `all_results.parquet` | `extract_data.py` | Absolute-path base stripped; only filename kept |

---

## 6. Orphan Script Nodes (no edges)

| Script | Reason |
|---|---|
| `generate_output.py` | Loop variable `filepath` unresolvable; f-string `.pdf` not in extension allowlist |
| `write_json_dump.py` | `open_write` fires instead of `json_dump`; `.json` not deliverable — suppressed |
| `write_numpy.py` | `np_save`/`np_savetxt` events parsed; `.npy`/`.txt` not deliverable — suppressed |
| `write_pickle.py` | `open_write` fires instead of `pickle_dump`; `.pkl` not deliverable — suppressed |

Note: `write_numpy.py` edges ARE parsed (events exist) but are filtered before graph export,
so the node appears as an orphan in the final graph.

---

## 7. Summary by Root Cause

| Root cause | Affected scripts | Classification |
|---|---|---|
| Extension not in `deliverable_extensions` + `suppress_internal_only_writes=True` | `write_numpy.py`, `write_json_dump.py`, `write_pickle.py` | By-design suppression; `.npy`, `.pkl`, `.json` treated as intermediate/non-deliverable |
| Write-pattern ordering: `open_write` pre-empts `json_dump`/`pickle_dump` | `write_json_dump.py`, `write_pickle.py` | **Bug**: more-specific patterns should have higher priority |
| Loop variable unresolvable | `generate_output.py` | Known limitation of sequential-assignment-only tracker |
| `.pdf` missing from f-string extension allowlist (`_FSTRING_WITH_EXT_RE`) | `generate_output.py` | **Gap**: placeholder fallback only covers data formats, not plot output formats |
| Function-scoped variable unresolvable | `analysis/plot_partial.py` | Known limitation; placeholder node correctly created |
| Absolute path stripping | `extract_data.py` | By-design; `was_absolute=True` diagnostic emitted |
| Path case normalization | `analysis/plot_basic.py` | By-design on Windows; potential cross-platform issue on Linux |
