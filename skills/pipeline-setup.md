---
name: pipeline-setup
description: >
  Installs data-pipeline-flow for the first time: creates a Python venv,
  installs the package, verifies Graphviz, identifies the project root, and
  runs a smoke-test render-image. Use for: install, set up, first time, new
  project, getting started. Do NOT trigger for re-renders or ongoing pipeline tasks.

allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---


## Goal

Get `data-pipeline-flow` installed and producing its first pipeline image on
a machine that does not yet have the tool configured. A successful run ends
with a non-empty PNG on disk and a minimal config file in place.

Not for: re-renders, cluster config, manual edges, or any task after initial setup.


---

## Routine

**Step 1 — Create venv and install**

Use full paths to venv binaries; do not activate the venv (activation does not
persist across Bash tool calls).

Windows:
```bash
py -3.11 -m venv .venv
.venv/Scripts/pip install -e ".[dev]"
```

macOS/Linux:
```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

If `.venv` already exists, skip creation but verify the entry point is present.

**Step 2 — Verify Graphviz**

```bash
dot --version
```

If this fails, stop and tell the user to install Graphviz and add `dot` to PATH.
Do not attempt `render-image` without it — the error will be cryptic.

**Step 3 — Identify project root**

Glob for `**/*.do`. If one candidate directory is obvious, propose it and confirm.
If ambiguous or missing, ask: *"Which folder contains your `.do` files?"*
A wrong root produces an empty graph with no error.

**Step 4 — Smoke-test render**

Windows:
```bash
.venv/Scripts/data-pipeline-flow render-image \
  --project-root <project-root> \
  --format png \
  --output <project-root>/viewer_output/pipeline.png
```

macOS/Linux:
```bash
.venv/bin/data-pipeline-flow render-image \
  --project-root <project-root> \
  --format png \
  --output <project-root>/viewer_output/pipeline.png
```

Verify the output file exists and is non-empty. If PNG shows no nodes, the
project root is wrong — repeat Step 3.

**Step 5 — Create starter config if absent**

Check for `pipeline_user_settings.yaml` in the repo root or
`<project-root>/user_configs/project_config.yaml`. If neither exists, write:

```yaml
project_root: "<project-root>"
display:
  view: overview
  theme: modern-light
```

The three default exclusion presets (`generated_outputs`, `archival_folders`,
`python_runtime`) are active automatically — no need to list them unless the
user wants to override them.

**Step 6 — Report**

State: venv location, Graphviz version, project root used, PNG path, config path.


---

## Gotchas

- **Wrong entry point** — Never use `python -m data_pipeline_flow`. The entry
  point is always `data-pipeline-flow` (the installed script in `.venv/Scripts/`
  or `.venv/bin/`).

- **Graphviz PATH on Windows** — Installers do not always add `dot` to PATH.
  If `dot --version` fails after a known install, prompt the user to add the
  Graphviz `bin/` folder to PATH and restart the shell.

- **Empty graph ≠ error** — If `render-image` succeeds but produces an empty
  PNG, the project root is wrong. No error is raised; the graph is just empty.

- **`--config` required for non-default config locations** — If config is stored
  outside the default locations, every CLI call needs an explicit `--config <path>`.
