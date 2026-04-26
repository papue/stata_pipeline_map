# FINDINGS — Python spurious "." / directory node from partial path resolution

## 1. Spurious node table

| Script | Pattern | Spurious node ID | What should appear instead |
|--------|---------|-----------------|---------------------------|
| `run_simulation.py` | `open("./" + PATH_PARAMETERS + ".json")` — runtime variable in middle | `.` | No node (unresolvable — variable unknown at parse time) |
| `scripts/load_runtime.py` | `pd.read_csv("../data/" + DATASET + ".csv")` — runtime variable as filename stem | `data` | No node (unresolvable — variable unknown at parse time) |
| `scripts/load_data.py` | `pd.read_csv("../data/" + DATASET + ".csv")` — DATASET is a literal `"train"` | `data/train` (missing `.csv`) | `data/train.csv` |
| `scripts/extra_patterns.py` | `os.path.join(prefix, name + ".pdf")` — directory prefix resolved, filename stem is runtime | `output/.pdf` | No node (unresolvable — `name` is unknown at parse time) |

## 2. Cases where partial resolution is correct (placeholder is acceptable)

- `scripts/extra_patterns.py` line 7: `f"./data/{env_var}.parquet"` — emits `data/*.parquet` (f-string placeholder node). This is the intended behavior: the f-string heuristic fires when a recognized file extension is present and no full resolution is possible. The `*` glob notation makes the placeholder obvious.

- `scripts/extra_patterns.py` line 20: `pd.read_csv(path3)` where `path3 = "" + "data.csv"` — emits `data.csv`. The empty-string base concatenates cleanly and produces the correct node.

## 3. Cases that already work correctly

- `scripts/load_config.py` (env-var-only path `"/" + ENV_PATH + "/config.yaml"`): produces **no events at all**. `ENV_PATH` is not in `vars_map`, the concatenation chain resolution fails, and no read match fires. This is correct behavior — an unknown runtime absolute path should not be emitted.
- `scripts/extra_patterns.py` empty-string concat: `base = ""` → `path3 = base + "data.csv"` → node `data.csv`. Works correctly.

## 4. Root cause — exact location in python_extract.py

### Bug A — spurious `.` node (`run_simulation.py`)

**File:** `src/data_pipeline_flow/parser/python_extract.py`, line **284** (`_FIXED_READ_PATTERNS`, `open_read` pattern).

**Mechanism:** The `open_read` regex captures the *first* quoted string inside `open(`. When the call is written as `open("./" + runtime_var + ".json")`, the pattern captures only `"./"` (group 1) because the remaining ` + runtime_var + ".json"` is outside the group. The raw path `"./"` is passed to `_add_event` (line **1154–1156** in the main read loop), which normalizes it to `"."` via `to_project_relative` → `normalize_token`. There is **no minimum-content check** — any non-empty captured string, including bare directory prefixes, is accepted as a valid node ID.

### Bug B — spurious `data` directory node (`scripts/load_runtime.py`)

**File:** `src/data_pipeline_flow/parser/python_extract.py`, line **284** (`_FIXED_READ_PATTERNS` / `_DEFAULT_PD_READ`).

**Mechanism:** Same as Bug A. `pd.read_csv("../data/" + DATASET + ".csv")` — `DATASET` is `sys.argv[1]`, not in `vars_map`. The `_STR_CONCAT_INLINE_RE` loop (line **1118**) looks for adjacent *already-quoted* strings; since `DATASET` is still a bare identifier at substitution time, no concat reduction fires. The read pattern captures only `"../data/"` (the first quoted token). After `../` normalization this becomes `data/` → normalized to `"data"` (a directory, not a file).

### Bug C — truncated `data/train` node, missing `.csv` (`scripts/load_data.py`)

**File:** `src/data_pipeline_flow/parser/python_extract.py`, line **1118** (`_STR_CONCAT_INLINE_RE` loop).

**Mechanism:** `DATASET = "train"` is in `vars_map`. Variable expansion on line **1091** rewrites `DATASET` to `"train"`, so the line becomes:
```
df = pd.read_csv("../data/" + "train" + ".csv")
```
`_STR_CONCAT_INLINE_RE.finditer(line)` (line 1118) is called **once** on the original line; the iterator yields only the *first* adjacent pair `"../data/" + "train"`, producing `"../data/train"`. The line becomes:
```
df = pd.read_csv("../data/train" + ".csv")
```
The iterator has already been exhausted — the second pair `"../data/train" + ".csv"` is **never processed**. The `pd.read_csv` pattern then captures `"../data/train"` (without `.csv`), and the node is emitted as `data/train`. The fix would be to re-run concat reduction in a `while`-loop (like the `for _ in range(5)` loop used for string division on line **1097**) rather than a single-pass `for _cm in finditer(line)`.

### Bug D — spurious `output/.pdf` node (`scripts/extra_patterns.py`)

**File:** `src/data_pipeline_flow/parser/python_extract.py`, lines **449–457** (`_resolve_ospath_join`).

**Mechanism:** For `os.path.join(prefix, name + ".pdf")`:
- `prefix` is resolved to `"../output"` from `vars_map` → appended to `parts`.
- `name + ".pdf"` is not a bare variable name, so the `elif piece in vars_map` branch is skipped.
- **However**, `_extract_quoted(piece)` on `'name + ".pdf"'` (line **451**) returns `".pdf"` — the literal suffix extracted from inside the compound expression — completely ignoring the `name +` prefix.
- `".pdf"` is appended to `parts` as if it were a complete filename.
- The joined result `"../output/.pdf"` normalizes to `"output/.pdf"`.

The root cause is that `_resolve_ospath_join` calls `_extract_quoted` on each comma-delimited argument piece without first checking whether the piece is a *pure* quoted literal or a compound expression. Any quoted substring found inside a compound expression (e.g., `name + ".pdf"`) is silently treated as the full argument value.
