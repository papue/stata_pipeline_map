# TOC duplicate sections — replication findings

## Confirmed duplicates

### analysis/extract_data.py (Python)

| Title | TOC line | Real header line |
|-------|----------|-----------------|
| 0. Helper functions | L3 | L11 |
| 0.1 Check Constant Action | L4 | L15 |
| 1. Collect averages per run | L5 | L22 |
| 2. Convert results to a df and save | L6 | L25 |

### analysis/run_models.r (R)

| Title | TOC line | Real header line |
|-------|----------|-----------------|
| 1. Load data | L2 | L8 |
| 2. Fit models | L3 | L11 |
| 3. Export results | L4 | L14 |

### analysis/master_analysis.do (Stata)

| Title | TOC line | Real header line |
|-------|----------|-----------------|
| 1. Load and clean data | L3 | L10 |
| 2. Run regressions | L4 | L13 |
| 3. Export tables | L5 | L16 |

## Adversarial cases

### analysis/two_phase.py — legitimate repeated heading (no TOC)

Both `## 1. Setup` lines are real section headers (L3 and L9). No early dense
cluster; the two occurrences are spread across the file body. A correct fix must
NOT suppress either entry.

Output (correct, both should be retained):
```
L3  [1]  1. Setup
L9  [1]  1. Setup
```

### analysis/mixed_toc.py — mixed TOC (one title does NOT recur)

TOC block at L2-L4 lists three titles: `0. Helper functions`, `1. Load data`,
`2. Process data`. Below the TOC, only titles 1 and 2 have real headers (L8,
L11). Title `0. Helper functions` appears only once (in the TOC only).

Because condition 3 fails (not all TOC titles recur), the conservative fallback
keeps the entire TOC cluster — so `0. Helper functions` at L2 is retained.
`1. Load data` and `2. Process data` appear twice each (TOC + real header).

Output (current — shows duplicates for L3/L8 and L4/L11):
```
L2  [1]  0. Helper functions
L3  [1]  1. Load data
L4  [1]  2. Process data
L8  [1]  1. Load data
L11 [1]  2. Process data
```

## Root cause

- `section_extract.py` emits matches regardless of whether the line is in a
  dense early TOC block or at the actual code position.
- No deduplication or TOC-block suppression logic exists.
- The extractor scans line-by-line; both the TOC reference and the real header
  match the same regex, producing two `Section` records per title.

## Fixture notes

- Python fixtures use `##` (multi-hash) comment style since the Python extractor
  does not detect single-`#` numbered comments.
- R fixtures use `## Title ----` (RStudio trailing-marker style) for the same
  reason.
- Stata uses `*` single-star numbered comments, which the Stata extractor detects.
