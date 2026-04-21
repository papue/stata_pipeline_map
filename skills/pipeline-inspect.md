---
name: pipeline-inspect
description: >
  Renders, explores, and diagnoses a data-pipeline-flow project. Use when
  the user asks "what does my pipeline look like", wants to render or re-render
  a pipeline image, validate or diagnose the graph, understand nodes/edges/clusters,
  or add a new analysis script. Does NOT handle installation, cluster config, or
  manual edges.

allowed-tools: Bash, Read, Glob, Grep, Write, Edit
---


## Goal

Enable the user to see, understand, and extend a data-pipeline-flow project.
A good result is a rendered graph, a plain-language explanation of any
diagnostics, and — if adding a new script — a confirmed node in the graph after
re-render.

Not for: first-time installation (use pipeline-setup), cluster config (use
pipeline-clusters), or manual edges (use pipeline-manual-edges).


---

## Routine

**venv path** — All CLI calls require the full venv path. Do not rely on PATH
activation (it doesn't persist across Bash calls). Use `.venv/Scripts/data-pipeline-flow`
on Windows or `.venv/bin/data-pipeline-flow` on macOS/Linux.

**Step 1 — Orient**

Locate config and project root. If a config file exists, note its path — it
must be passed explicitly with `--config` on every CLI call.

```bash
# Check common config locations
ls '<project-root>/pipeline_user_settings.yaml' 2>/dev/null
ls '<project-root>/user_configs/project_config.yaml' 2>/dev/null
```

**Step 2 — Run summary and read edge CSV**

```bash
.venv/Scripts/data-pipeline-flow summary \
  --project-root <project-root> \
  --config <config-path>        # omit only if no config file exists
```

Then read the edge CSV. It encodes the full dependency graph as flat rows and
is far cheaper than reading individual scripts (~2k tokens vs reading all code).

Default location: `<project-root>/viewer_output/parser_edges.csv`

**Step 3 — Render the image**

```bash
.venv/Scripts/data-pipeline-flow render-image \
  --project-root <project-root> \
  --config <config-path> \
  --format png \
  --output <project-root>/viewer_output/pipeline.png
```

Use `--format svg` or `pdf` if requested. The view (overview / deliverables /
scripts_only / stage_overview / technical) is set via `display.view` in the
config YAML, not as a CLI flag.

**Step 4 — Validate and explain diagnostics**

```bash
.venv/Scripts/data-pipeline-flow validate \
  --project-root <project-root> \
  --config <config-path>
```

Key diagnostic codes:

| Code | Meaning |
|------|---------|
| `missing_input` | Script reads a file no other script writes — check for path typo or add a manual edge |
| `duplicate_writer` | Two scripts write the same file — check which is canonical |
| `orphan_script` | Script has no edges — may be standalone, excluded, or paths are dynamic |
| `absolute_path` | Parser cannot trace an absolute path — normalize to project-relative |
| `manual_edge_node_not_found` | A `manual_edges` entry references a missing node — path is stale |

**Step 5 — Adding a new analysis script**

When the user wants to add a new script:

1. Read the edge CSV to identify which existing nodes the new script will consume or produce.
2. Propose: folder, filename, what it reads, what it writes.
3. Confirm with user, write the script.
4. Re-run `summary` and `render-image` — confirm the new node and its edges appear.

No need to read upstream source files for style — the tool output is enough.

**Step 6 — Report**

State: output path, node/edge counts from summary, any diagnostics needing attention.
If a new script was added: confirm its node ID and edges in the graph.


---

## Gotchas

- **`--config` is never auto-discovered.** Even if the config sits at the project
  root, the CLI will not find it without an explicit `--config <path>`. Omitting
  it silently uses defaults and may produce a different graph.

- **`--view` is not a CLI flag.** Set `display.view` in the config YAML. To do
  a one-off render with a different view, edit the config, render, then restore.

- **Read edge CSV before source scripts.** Do not open `.do`/`.py`/`.R` files to
  understand the graph — the edge CSV gives you the full picture in one flat file.

- **Empty graph is not an error.** If `render-image` succeeds but the PNG is
  empty, the project root is wrong or all files are excluded.
