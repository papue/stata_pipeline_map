# Chained globals — replication findings

## Single-script chain

- Working: **yes**

Within `single_script/analysis.do`, `$root` is set first, then `$rawdir` and `$outdir` are
defined using `${root}`. Because globals are processed line-by-line within a single parse,
`$root` is already in `globals_map` when the chained definitions are reached, so both expand
correctly.

Edges produced:
- `data/project/raw/survey.dta` → `single_script/analysis.do` (use)
- `single_script/analysis.do` → `data/project/output/survey_clean.dta` (save)

---

## Cross-script chain (two-level)

`master.do` sets `$root = "data/project"`, then calls `pipeline/stage1.do` and
`pipeline/stage2.do`. Each child is parsed with an empty `globals_map`.

| Script | Global used | Defined in | Root global from | Expected value | Actual |
|--------|-------------|-----------|-----------------|----------------|--------|
| stage1.do | `${root}` | master.do | master.do | `data/project` | unresolved (`{root}`) |
| stage1.do | `${outdir}` | stage1.do (self) | master.do via `${root}` | `data/project/processed` | unresolved (`{root}/processed`) |
| stage2.do | `${outdir}` | stage1.do | master.do ($root) | `data/project/processed` | unresolved (`{outdir}`) |

Edges actually produced for the cross-script portion:
- `{root}/raw/input.dta` → `pipeline/stage1.do` (placeholder — `$root` unresolved)
- `pipeline/stage1.do` → `{root}/processed/stage1_out.dta` (placeholder)
- `{outdir}/stage1_out.dta` → `pipeline/stage2.do` (placeholder — `$outdir` not inherited)
- `pipeline/stage2.do` → `{outdir}/stage2_final.dta` (placeholder)

Note: stage2.do also uses `${outdir}`. Stage1 defines `$outdir` in its own scope, but
because both stage1.do and stage2.do are parsed independently (both children of master.do),
stage2.do's `globals_map` is empty — it never sees `$outdir` at all.

---

## Three-level chain

`master2.do` sets `$proj = "studies/welfare"` and `$datadir = "${proj}/data"`. Because
`$proj` is resolved within master2.do's own parse, `$datadir` is stored correctly as
`studies/welfare/data`. Then `analysis/clean.do` is called.

`clean.do` starts with an empty `globals_map`. It defines `$rawdir = "${datadir}/raw"` but
`$datadir` is not in scope, so `$rawdir` is stored as `{datadir}/raw`.

| Script | Global used | Defined in | Expected value | Actual |
|--------|-------------|-----------|----------------|--------|
| clean.do | `${datadir}` | master2.do | `studies/welfare/data` | unresolved (`{datadir}`) |
| clean.do | `${rawdir}` | clean.do (self) | `studies/welfare/data/raw` | unresolved (`{datadir}/raw`) |

Edges actually produced:
- `{datadir}/raw/survey.dta` → `analysis/clean.do` (placeholder)
- `analysis/clean.do` → `{datadir}/clean/survey_clean.dta` (placeholder)

The chain is doubly broken: `$datadir` itself arrives unresolved, and `$rawdir` (which
depends on `$datadir`) is therefore also stored unresolved. Any grandchild that inherits
`$rawdir` would receive a doubly-broken placeholder value.

---

## Key failure mode

Each script is parsed by an independent call to `stata_extract.py` with a fresh
`globals_map: dict[str, str] = {}` initialised on entry (stata_extract.py line ~334).
No globals survive across the call boundary. The `child_scripts` list returned by the
parser is used only to build script-call edges; the parent's accumulated globals are
never forwarded to child parsers.

Consequence: any global defined in a parent and used in a path expression in a child
produces a `dynamic_path_partial_resolution` diagnostic and a placeholder node.

When a child also _defines_ a new global using an inherited one (e.g.
`global outdir "${root}/processed"`), the child stores the new global with an unresolved
segment. If a grandchild then inherits that child-defined global, it receives an already-
broken value — the chain is broken at every link simultaneously.

---

## Diagnostics observed (six `dynamic_path_partial_resolution`)

| Script | Line | Pattern |
|--------|------|---------|
| analysis/clean.do | 3 | `{datadir}/raw/survey.dta` |
| analysis/clean.do | 4 | `{datadir}/clean/survey_clean.dta` |
| pipeline/stage1.do | 3 | `{root}/raw/input.dta` |
| pipeline/stage1.do | 4 | `{root}/processed/stage1_out.dta` |
| pipeline/stage2.do | 2 | `{outdir}/stage1_out.dta` |
| pipeline/stage2.do | 3 | `{outdir}/stage2_final.dta` |

An additional `ambiguous_name` diagnostic was raised because both `{outdir}/stage1_out.dta`
(from stage2.do) and `{root}/processed/stage1_out.dta` (from stage1.do) are separate
placeholder nodes that share the filename `stage1_out.dta` — confirming the broken
cross-script link.

---

## Fix dependency

This is fixed by CSG-02 IF the inherited globals are seeded BEFORE the child's own `global`
statements are processed in the line loop. See CSG-02 for implementation guidance.

Specifically: `multi_extract.py` must collect the parent's `globals_map` after parsing and
pass it as `inherited_globals` to each child's parse call. Inside `parse_do_file`, those
inherited globals must be merged into `globals_map` before the line loop begins — so that
chained definitions like `global outdir "${root}/processed"` expand correctly on the first
pass through the child script.
