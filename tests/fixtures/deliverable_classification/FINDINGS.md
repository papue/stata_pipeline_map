# Deliverable classification bug — findings

## Classification results

| File | Written by | Read by | Node role (snapshot) | Edge kind (write) | Expected role |
|------|-----------|---------|---------------------|-------------------|--------------|
| results/all_results.parquet | extract_data.py | generate_graphs.py | generated_artifact | deliverable | intermediate |
| results/summary.csv | extract_data.py | generate_graphs.py | generated_artifact | deliverable | intermediate |
| results/summary.xlsx | extract_data.py | generate_graphs.py | generated_artifact | deliverable | intermediate |
| output/final_table.csv | final_report.py | nobody | deliverable | deliverable | deliverable |
| output/plot.png | generate_graphs.py | nobody | deliverable | deliverable | deliverable |

## Observed behaviour

Node roles from `snapshot-json`:
- `results/all_results.parquet` → `generated_artifact`
- `results/summary.csv` → `generated_artifact`
- `results/summary.xlsx` → `generated_artifact`
- `output/final_table.csv` → `deliverable`
- `output/plot.png` → `deliverable`

Edge kinds from `extract-edges` (edges.csv):
- Write edges for all three intermediate files: `deliverable`
- Read edges for all three intermediate files: `generated_artifact`

The two representations are **inconsistent**: the write edge says `deliverable` but the
node stored in the graph says `generated_artifact`.

## Root cause confirmed

- `_classify_artifact_generic` in `multi_extract.py`, line 156:
  ```
  if is_write and suffix in deliverable_extensions:
      return 'deliverable'
  ```
- `deliverable_extensions` set (config/schema.py line 75) includes `.parquet`, `.csv`,
  `.xlsx`, `.feather`, `.rds`, `.rdata`, `.rda` — and also `.dta`.
- `consumers` dict is built (line 593) and consulted at line 626, but only to decide
  whether to *suppress display* of the pair (add to `suppressed_internal_only`), not to
  downgrade the classification from `deliverable` to `intermediate`.
- Line 626 guard: `if role != 'deliverable' and consumers.get(p, set()) <= {script}:`
  — because `role == 'deliverable'` this condition is False, so the pair is never
  suppressed and the `deliverable` classification is never overridden.
- `.dta` carve-out: line 158–159 only triggers on the *read* path (`is_write=False`,
  `producer_exists=True`), returning `intermediate`. On the *write* path, `.dta` is still
  classified `deliverable` by line 156 before the carve-out is reached.

## Why node role ≠ edge kind

`graph.add_node` uses `setdefault` (entities.py line 56), so the first `add_node` call
for a given node_id wins. The reads loop (line 636) runs before the writes loop
(line 674). For the three intermediate files, the reads loop calls
`_classify_artifact_generic` with `is_write=False`, `producer_exists=True` → returns
`generated_artifact`, and stores that as the node role. The subsequent writes loop
attempts to re-add the same node with `role='deliverable'` but the `setdefault` call is
a no-op. This is why the snapshot shows `generated_artifact` while the write edge kind
shows `deliverable`.

## Consumer check: is it applied?

The consumer check exists (line 626) but it does **not** affect classification. It only
suppresses display of pairs where `role != 'deliverable'`. Files classified as
`deliverable` skip the check entirely due to the `role != 'deliverable'` guard. A truly
correct fix would require passing consumer information *into*
`_classify_artifact_generic` so it can return `intermediate` (or `generated_artifact`)
when the file is consumed downstream.
