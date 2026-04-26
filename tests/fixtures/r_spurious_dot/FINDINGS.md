# Findings: R Spurious "." Node from Partial Path Resolution

## Summary

The fixture scripts as written produce **silent drops** (no edges, no spurious nodes) for all
dynamic patterns, because partial-path resolution is only applied to the **write** pass (lines
1039–1056 of `r_extract.py`). Read patterns (`read.csv`, `fromJSON`, etc.) are never retried
with partial resolution, so unresolvable reads are silently discarded rather than emitting a
placeholder node.

However, a closely related pattern **does** produce a spurious `"."` node: when a variable is
assigned the literal result of `file.path(".")` or `paste0("./")` (no runtime argument), the
resolver stores `"."` as the variable's value. Any subsequent `read.csv(var)` then expands to
`read.csv(".")` and emits a node with id `"."` — a bare directory, not a file.

---

## Table: Script | Pattern | Actual output | What should appear instead

| Script | Pattern | Node/edge emitted | Expected |
|--------|---------|-------------------|----------|
| `run_simulation.R` | `fromJSON(paste0("./", param_file, ".json"))` — `param_file` is runtime | **No event (silent drop)** | No edge (correct to drop); or a diagnostic noting the unresolvable read |
| `scripts/load_dynamic.R` | `read.csv(file.path(".", config_name))` — `config_name` is runtime | **No event (silent drop)** | No edge (correct to drop); or a diagnostic |
| `scripts/load_wave.R` | `read.csv(paste0("../data/wave_", wave, ".csv"))` — `wave` is runtime | **No event (silent drop)** | No edge (correct to drop); or a diagnostic |
| `scripts/load_known.R` | `read.csv(paste0("../data/", suffix, ".csv"))` — `suffix = "final"` (literal) | Edge: `data/final.csv → scripts/load_known.r` | Correct — this is the expected result |

**Observed nodes in graph:** `run_simulation.r`, `scripts/load_dynamic.r`, `scripts/load_wave.r`,
`scripts/load_known.r` (all scripts from discovery), plus `data/final.csv` (from the one
resolved edge). No spurious `"."` node.

---

## Section: The latent spurious-dot bug (not triggered by these fixtures)

Although the fixture scripts as written do not trigger the bug, the following **minimal
reproduction** confirms it exists in the same extractor:

```r
# triggers spurious "." node
path <- file.path(".")
df <- read.csv(path)
```

**What happens:**
1. `_resolve_path_args("\".\",", {})` at line 301 returns `"."` (single component, no filename
   check).
2. `vars_map["path"] = "."` is stored during the second-pass var resolution (line 822–827).
3. Line `df <- read.csv(path)` expands to `df <- read.csv(".")` after variable substitution
   (line 998).
4. `_try_match` fires the `read_csv` pattern, returning raw path `"."`.
5. `_add_event` is called with `raw_path="."`. `to_project_relative(root, Path("."))` returns
   `"."`. `normalize_token(".")` returns `"."`.
6. Node `"."` is emitted — a bare project-root directory, not a file.

Same outcome for `paste0("./")` directly in `read.csv`: `_resolve_paste0_args` returns `"./"`,
which satisfies the `'.' in resolved` check at line 508/589, so it is substituted and matched.

---

## Section: Control cases (already correct)

| Script | Pattern | Result |
|--------|---------|--------|
| `scripts/load_known.R` | `suffix <- "final"` (literal); `read.csv(paste0("../data/", suffix, ".csv"))` | Correct edge: `data/final.csv → scripts/load_known.r` |

`suffix` is a literal string assignment, captured by `_VAR_ASSIGN_RE` in the first pass. The
full `paste0` resolution fires without `is_partial`, producing `../data/final.csv`. The relative
path is resolved through `_add_event` → `(r_file.parent / raw_path).resolve()` → normalized to
`data/final.csv`.

---

## Section: Root cause

**Primary location: `_resolve_path_args` — `r_extract.py` lines 301–315**

```python
def _resolve_path_args(args_text: str, vars_map: dict[str, str]) -> str | None:
    parts = []
    for piece in args_text.split(','):
        ...
    return '/'.join(parts) if parts else None
```

This function returns the joined string of all resolved components with no guard against the
result being a bare directory reference (e.g., `"."`, `"./"`, `"data"` with no extension). A
single-component `file.path(".")` call returns `"."` — a valid non-None string that passes all
downstream checks.

**Secondary location: `_add_event` — `r_extract.py` lines 899–927**

```python
def _add_event(line_no, command, raw_path, is_write):
    ...
    norm, was_abs = to_project_relative(project_root, Path(resolved_path), normalization)
    norm = normalize_token(norm)
    ...
    events.append(ParsedEvent(..., normalized_paths=[norm], ...))
```

`_add_event` has no guard that checks whether `norm` looks like a file (e.g., has an extension,
or is not just `"."` / `"./"` / a bare directory name without a `.` in the final component).
Any non-excluded, non-external, non-empty string is emitted as a node.

**Why the fixture scripts do NOT trigger it:**

- `run_simulation.R`, `load_dynamic.R`, `load_wave.R`: the dynamic variables (`param_file`,
  `config_name`, `wave`) come from `args[1]` — not literal assignments — so they are never
  added to `vars_map`. The path helpers (`paste0`, `file.path`) fail to resolve (return `None`)
  and the read call stays as `read.csv(path)` with `path` unexpanded. No pattern matches.
- The partial-resolution pass (lines 1039–1056) covers only **write** patterns; unresolvable
  reads are silently dropped.

**Trigger condition for spurious `"."` node:**

A variable must be assigned a fully-resolvable value that is a bare directory (`"."`, `"./"`,
an existing directory path with no filename), and that variable must subsequently be used as
the sole path argument to a read function. This can happen when:
- `file.path(".")` is used alone (common idiom for "current directory"),
- `paste0("./")` is used alone,
- or a multi-component path helper omits the filename component and the partial result happens
  to be directory-only.
