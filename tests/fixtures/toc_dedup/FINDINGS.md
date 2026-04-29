# TOC dedup bug — findings

## extract_data.py — sections output

| Line | Level | Title | Is TOC entry or real header? |
|------|-------|-------|------------------------------|
| 1 | 1 | Table of contents | TOC block header |
| 2 | 1 | 0. Helper functions | TOC entry |
| 3 | 2 | 0.1 Check Constant Action | TOC entry |
| 4 | 1 | 1. Collect data | TOC entry |
| 5 | 1 | 2. Save results | TOC entry |
| 9 | 1 | 0. Helper functions | Real header |
| 14 | 2 | 0.1 Check Constant Action | Real header |
| 19 | 2 | 0.2 Validate data | Real header only (not in TOC) |
| 24 | 1 | 1. Collect data | Real header |
| 28 | 1 | 2. Save results | Real header |

Duplicated titles (appear as both TOC entry and real header):
- "0. Helper functions" — L2 (TOC) and L9 (real)
- "0.1 Check Constant Action" — L3 (TOC) and L14 (real)
- "1. Collect data" — L4 (TOC) and L24 (real)
- "2. Save results" — L5 (TOC) and L28 (real)

Note: "0.2 Validate data" appears only as a real header (L19); it was NOT listed in the TOC.
Note: "Table of contents" (L1) appears as a spurious section title entry.

## generate_output.py — sections output

| Line | Level | Title | Is TOC entry or real header? |
|------|-------|-------|------------------------------|
| 1 | 1 | Table of contents | TOC block header |
| 2 | 1 | 1. Import data | TOC entry |
| 3 | 1 | 2. Boxplots | TOC entry |
| 4 | 2 | 2.1 Define Function | TOC entry |
| 5 | 2 | 2.2 Generate Figures | TOC entry |
| 6 | 1 | 3. Boxplots - comparing cases | TOC entry |
| 10 | 1 | 1. Import data | Real header |
| 15 | 1 | 2. Boxplots - by case | Real header |
| 19 | 2 | 2.1 Define Function | Real header |
| 25 | 2 | 2.2 Generate Figures | Real header |
| 30 | 1 | 3. Boxplots - comparing cases | Real header |

Near-duplicate pair (TOC "2. Boxplots" vs real "2. Boxplots - by case"):
- Both present? Yes — "2. Boxplots" at L3 (TOC entry) and "2. Boxplots - by case" at L15 (real header)
- Counts as duplicate or separate entry? Separate entries — the titles differ, so exact-match dedup would NOT catch this pair

Exact duplicates in generate_output.py:
- "1. Import data" — L2 (TOC) and L10 (real)
- "2.1 Define Function" — L4 (TOC) and L19 (real)
- "2.2 Generate Figures" — L5 (TOC) and L25 (real)
- "3. Boxplots - comparing cases" — L6 (TOC) and L30 (real)

## Root cause confirmed
- TOC block (lines 1-5 / 1-6) uses the same `###` marker as real section headers
- Extractor has no TOC detection logic: it matches any line starting with `###` regardless of whether it is in a dense listing block at the top or a real section header in the body
- Dedup-by-exact-title: would it catch the "2. Boxplots" / "2. Boxplots - by case" pair? NO — the titles differ by " - by case"; only the four exactly-matching pairs would be deduplicated; this near-duplicate pair would survive

## Tool invocation

Command:
```
data-pipeline-flow extract-sections --project-root tests/fixtures/toc_dedup --output /tmp/nh09_sections.json
```

Tool output: "Scripts with sections: 7" (includes other pre-existing fixture scripts in the directory)
