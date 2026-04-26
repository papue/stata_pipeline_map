# MO-17: Stata Multi-Macro Path Concat — Replication Findings

## Summary

All 7 fixture scripts produce **correct edges** both before and after the MO-18 fix.
The pre-fix bugs were not missing edges but **false-positive `absolute_path_usage`
warnings** triggered by `_resolve_script_relative` converting `../` relative paths
into absolute system paths before `to_project_relative` saw them.

---

## Edge Table (post-fix, all 9 edges correct)

| Source node | Target script | Command | Pattern |
|-------------|--------------|---------|---------|
| data/processed/results.dta | scripts/two_globals.do | use | two globals |
| data/processed/output.dta | scripts/two_globals.do (written by) | save | two globals |
| data/analysis/results.dta | scripts/composed_global.do | use | composed $full |
| data/results_v2.dta | scripts/mixed_macros.do | use | mixed global+local |
| data/output_v2.dta | scripts/mixed_macros.do (written by) | save | mixed global+local |
| data/analysis.dta | scripts/local_chain.do | use | local chain |
| data/results.dta | scripts/two_locals_backslash.do | use | backslash locals |
| data/raw/source.dta | scripts/three_chain.do | use | three-level chain |
| data/wave_1.dta | scripts/numeric_local.do | use | numeric local |

---

## Working Patterns (all resolved correctly)

| Script | Pattern | Resolution |
|--------|---------|-----------|
| two_globals.do | `$root/$subdir/x.dta` — two globals joined with `/` | WORKS — expand() joins stored global values |
| composed_global.do | `global full "$root\$sub\results.dta"` then `use "$full"` | WORKS — expand() called on global value at definition time; backslashes normalized |
| mixed_macros.do | `"$datadir/results_\`variant'.dta"` — global + local | WORKS — expand() runs first, then local token substitution |
| local_chain.do | `local file "\`base'/analysis.dta"` then `use "\`file'"` | WORKS — second-pass local resolution handles nested locals |
| two_locals_backslash.do | `` "`dir'\\`name'.dta" `` — two locals, backslash separator | WORKS — backslash in result normalized to forward slash |
| three_chain.do | `$root → $sub1 → $sub2` three-level global chain | WORKS — expand() while-loop handles transitive globals |
| numeric_local.do | `` "../data/wave_`i'.dta" `` — numeric local in path | WORKS — single local token expansion |

---

## Bugs Found and Fixed (MO-18)

### Bug 1: False-positive `absolute_path_usage` warnings

**Affected scripts:** two_globals.do, local_chain.do, mixed_macros.do,
two_locals_backslash.do, numeric_local.do (5 of 7)

**Root cause:** `_resolve_script_relative()` converts relative `../data/x.dta`
paths to full absolute system paths (e.g. `D:\...\data\x.dta`) so that
`posixpath.normpath` can collapse `..`. Then `to_project_relative()` receives an
absolute path and sets `was_absolute=True`, even though the original Stata source
used a relative path.

**Fix:** Check `originally_absolute` on `expanded` before calling
`_resolve_script_relative`. Only propagate `was_absolute=True` when the path was
already absolute before the relative resolution step.

**Before:** 7 `absolute_path_usage` warnings
**After:** 2 (both genuine — `C:\project\...` literals in composed_global.do and three_chain.do)

### Bug 2: Missing multi-pass global expansion after local substitution

**Root cause:** After the second-pass local expansion, results could still contain
`$global` references embedded in local values (e.g. `local base "$datadir"`).
The second pass only re-checked for nested local tokens but did not call `expand()`
again with globals_map.

**Fix:** The multi-pass loop now calls `expand(path_str, globals_map)` on each
candidate before checking for remaining local tokens. Up to 3 total passes.

### Bug 3: Backslash normalization after substitution

**Root cause:** After all substitution was complete, paths still containing Windows
`\` separators were not normalized to `/` before being returned.

**Fix:** After the multi-pass loop, each final candidate has `.replace('\\', '/')`
applied before deduplication.

---

## Additional Patterns Tested (brainstormed)

| Pattern | File | Result |
|---------|------|--------|
| Three-level global chain (`$A → $B → $C`) | three_chain.do | WORKS |
| Numeric loop variable in path | numeric_local.do | WORKS |
| Backslash path separator in local | two_locals_backslash.do | WORKS |

---

## Remaining Expected Gaps (not in this fixture set)

- `local` value containing a `$global` reference (indirect):
  `local base "$datadir"` then `` use "`base'/x.dta" `` — the multi-pass fix now handles this.
- Dynamic paths using `c(sysdir_*)` or other Stata system macros — still partial.
- Paths constructed via `local path = "\`a'' + "/" + "\`b''"` (string concatenation
  with `=` computed) — stored via LOCAL_COMPUTED_RE and not expanded.
