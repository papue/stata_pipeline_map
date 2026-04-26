# Findings: Stata Spurious Node / Partial Macro Resolution

Fixture project: `tests/fixtures/stata_spurious_dot/`
Tool run: `extract-edges` + `snapshot-json`

---

## 1. Node ID Table

| Script | Stata pattern | Node ID produced | What should appear instead |
|---|---|---|---|
| `scripts/run_model.do` | `use "./${scenario}.dta"` — `$scenario` is a local, NOT a global | `{scenario}.dta` (root-level placeholder) | `{scenario}.dta` at root is acceptable, but the leading `./` directory prefix is silently discarded. The real bug is that `$scenario` is never resolved against `local_map`, so the node is marked partial when a fully-known local value exists. |
| `scripts/run_model.do` | `save "./${scenario}_results.dta"` — same issue | `{scenario}_results.dta` | Same as above. |
| `scripts/load_param.do` | `use "../data/${TABLE_NAME}.dta"` — `TABLE_NAME` undefined everywhere | `data/{table_name}.dta` | Acceptable partial placeholder. `TABLE_NAME` is case-folded to `table_name` by `normalize_token`. This is a legitimate diagnostic, not a bug. |
| `scripts/run_spec.do` | `use "../results/\`spec'_output.dta"` where `local spec "\`1'"   /* runtime positional argument */` | **6 nodes**: `results/"\`1'"_output.dta`, `results/*_output.dta`, `results/runtime_output.dta`, `results/positional_output.dta`, `results/argument_output.dta`, `results/*/_output.dta` | One node: `results/{1}_output.dta` (or `results/{dynamic}_output.dta`). The 6 spurious nodes are generated because `LOCAL_RE` captures the inline `/* ... */` comment as part of the local value, then `_collect_local_values` word-splits it into 6 separate values which are all expanded via Cartesian product. |
| `scripts/run_known.do` | `use "../data/results_\`variant'.dta"` where `local variant "v2"` | `data/results_v2.dta` (correct, status=full) | Correct — this is the control case. |

---

## 2. Control Cases (Already Correct)

**`scripts/run_known.do`**

```stata
local variant "v2"
use "../data/results_`variant'.dta", clear
```

- `variant` is defined statically as `"v2"`.
- `_collect_local_values("\"v2\"")` correctly produces `['v2']`.
- `_resolve_dynamic_path` substitutes `\`variant'` → `v2`, giving `../data/results_v2.dta`.
- `_resolve_script_relative` resolves the `..` against `scripts/` to an absolute path.
- `to_project_relative` strips the project root prefix → `data/results_v2.dta`.
- Resolution status: `full`. No diagnostic emitted. Correct behavior.

**`scripts/load_param.do`**

```stata
use "../data/${TABLE_NAME}.dta", clear
```

- `TABLE_NAME` is a dollar-form reference that is not defined in `globals_map`.
- `DOLLAR_GLOBAL_RE` correctly detects it as unresolved.
- Partial path `../data/{TABLE_NAME}.dta` is normalized to `data/{table_name}.dta`.
- Diagnostic `dynamic_path_partial_resolution` is emitted. Correct behavior: undefined global → partial placeholder.

---

## 3. Root Causes

### Bug A — Dollar-form local references are never resolved (run_model.do)

**File:** `src/data_pipeline_flow/parser/stata_extract.py`

**Lines 112–122 (`expand`) and 143–151 (`_resolve_dynamic_path`)**

```python
# Line 112-122: expand() only consults globals_map
def expand(path_expr: str, globals_map: dict[str, str]) -> str:
    ...

# Line 143-151: DOLLAR_GLOBAL_RE finds unresolved $name refs and returns partial
dollar_matches = DOLLAR_GLOBAL_RE.findall(expanded)
if dollar_matches:
    # At least one ${name} or $name reference was not resolved by expand()
    placeholder = expanded
    for braced, bare in dollar_matches:
        name = braced or bare
        placeholder = placeholder.replace(f'${{{name}}}', f'{{{name}}}')
        placeholder = re.sub(rf'\${re.escape(name)}(?!\w)', f'{{{name}}}', placeholder)
    return [placeholder], 'partial', placeholder
```

In Stata, `$name` and `\`name'` are equivalent ways to reference a local macro. However, `expand()` only checks `globals_map`. When a script uses `local scenario "\`1'"` and then `use "./${scenario}.dta"`, the dollar-form `${scenario}` is never looked up in `local_map`. The early-return at line 151 fires before any local expansion is attempted, marking the result as `partial` and emitting a placeholder `{scenario}.dta` — even though the local's value IS in scope (albeit itself unresolvable at static analysis time, since it is `"\`1'"` — a positional argument).

**Effect:** Node `{scenario}.dta` appears at the project root instead of `{scenario}.dta` (same in this case, but the diagnostic marks it partial for the wrong reason). If `local scenario "baseline"` were used, the correct result would be `baseline.dta`; instead, `{scenario}.dta` appears.

---

### Bug B — LOCAL_RE captures inline `/* ... */` comments (run_spec.do)

**File:** `src/data_pipeline_flow/parser/stata_extract.py`

**Line 16 (`LOCAL_RE`) and line 367 (`_collect_local_values` call)**

```python
# Line 16
LOCAL_RE = re.compile(r'^\s*local\s+(\w+)\s+(.+?)\s*$', re.I)

# Line 366-367
local = LOCAL_RE.search(line)
if local:
    local_map[local.group(1)] = _collect_local_values(local.group(2))
```

For the line:
```stata
local spec "`1'"   /* runtime positional argument */
```

`LOCAL_RE` group 2 captures everything after `spec ` to end-of-line: `'"\`1\'"   /* runtime positional argument */'`. `_collect_local_values` (lines 125–127) strips outer quotes then splits on whitespace, yielding:
```
['"`1\'"', '/*', 'runtime', 'positional', 'argument', '*/']
```
Six values. These are stored in `local_map['spec']`. When `_resolve_dynamic_path` later substitutes `\`spec'` via Cartesian product, it generates 6 path expansions, one for each value. After normalization, 6 distinct placeholder nodes appear in the graph.

**Effect:** 6 spurious artifact_placeholder nodes are created from a single `use` command:
- `results/"\`1'"_output.dta`
- `results/*_output.dta`
- `results/runtime_output.dta`
- `results/positional_output.dta`
- `results/argument_output.dta`
- `results/*/_output.dta`

All 6 edges (`use`) point from each of these spurious nodes to `scripts/run_spec.do`.

---

## 4. Why No Literal "." Node in This Fixture

The task name mentions a spurious `"."` node. This arises when a resolved path is exactly `"."` or `"./"`. In the current fixtures:

- `"./${scenario}.dta"` resolves partially to `./{scenario}.dta`, which after `to_project_relative` strips the `./` prefix, yielding `{scenario}.dta` — the directory component is dropped cleanly.
- `"."` and `"./"` would only reach the graph as node IDs if they matched a command regex (e.g., `USE_RE`, `SAVE_RE`). These regexes require a literal `.` in the path (file extension), so a bare `"."` does not match.

A `"."` node CAN appear if `to_project_relative` receives a path that resolves to `"."` and is still passed through `normalize_token`. The normalization chain:

```
'.'   -> to_project_relative -> '.'
'./'  -> to_project_relative -> '.'
normalize_token('.') -> '.'
```

This would occur if a partial placeholder such as `"./{dynamic}"` (where `{dynamic}` = placeholder_token with no `.` suffix) were emitted — but current regexes require a file extension, so this path is not reached with the current fixture patterns. The related risk is present in `_resolve_dynamic_path` lines 158–168 when `missing` tokens are replaced with `{token}` and no suffix guard exists.

---

## 5. Evidence

**Raw edge CSV output** (`viewer_output/parser_edges.csv`):
```
source,target,command,kind
scripts/run_model.do,run_model.do,do,script_call
data/{table_name}.dta,scripts/load_param.do,use,placeholder_artifact
data/results_v2.dta,scripts/run_known.do,use,reference_input
{scenario}.dta,scripts/run_model.do,use,placeholder_artifact
"results/"`1\'"_output.dta",scripts/run_spec.do,use,placeholder_artifact
results/*/_output.dta,scripts/run_spec.do,use,placeholder_artifact
results/*_output.dta,scripts/run_spec.do,use,placeholder_artifact
results/argument_output.dta,scripts/run_spec.do,use,placeholder_artifact
results/positional_output.dta,scripts/run_spec.do,use,placeholder_artifact
results/runtime_output.dta,scripts/run_spec.do,use,placeholder_artifact
scripts/run_model.do,{scenario}_results.dta,save,placeholder_artifact
```

**Summary output**: 15 nodes (scripts=5, artifacts=1), 11 edges, 10 diagnostics.
