---
name: pipeline-clusters
description: >
  Configures clusters and meta-clusters in a data-pipeline-flow project config.
  Use when the user wants to group scripts into logical sections, organize
  pipeline stages, nest clusters into parent groups, or change clustering strategy.
  Trigger phrases: cluster, group scripts, organize pipeline, meta-cluster, nest
  clusters, logical grouping. Does NOT handle rendering, manual edges, or installation.

allowed-tools: Read, Write, Edit, Glob, Grep, Bash
---


## Goal

Configure the `clusters:` and `clustering:` blocks in the project config so the
rendered diagram groups related nodes into labeled boxes, with optional
meta-cluster nesting. A good result renders without errors and shows the intended
groupings.

Not for: first-time installation (use pipeline-setup), rendering without config
changes (use pipeline-inspect), or manual edges (use pipeline-manual-edges).


---

## Routine

**venv path** — All CLI calls require the full venv path. Do not rely on PATH
activation (it doesn't persist across Bash calls). Use `.venv/Scripts/data-pipeline-flow`
on Windows or `.venv/bin/data-pipeline-flow` on macOS/Linux.

**Step 1 — Orient**

Read the project config and current `clusters:` list. Then see what nodes exist:

```bash
.venv/Scripts/data-pipeline-flow summary --project-root <project_root> --config <config_path>
```

Use Glob on `**/*.do` (and `**/*.py`, `**/*.R`) if node names alone are not
enough to propose sensible groupings.

**Step 2 — Design the cluster layout**

Rules:
- `members` = project-relative file paths — leaf cluster only
- `member_cluster_ids` = list of cluster IDs — meta-cluster only
- These are **mutually exclusive** on a single entry
- Paths in `members` are relative to `project_root`, not to the config file
- `order` (integer) controls render order; gaps are fine
- `collapse: true` renders the cluster as a single summary node
- `strategy: auto` — auto-infers clusters and layers explicit ones on top
- `strategy: manual` — only explicit clusters appear; nodes not listed disappear with no warning

**Step 3 — Write the config blocks**

```yaml
clustering:
  strategy: auto   # or: manual

clusters:
  - id: data_prep
    label: "Data Preparation"
    order: 1
    members:
      - 01_data/02_scripts/01_import.do
      - 01_data/02_scripts/02_clean.do

  - id: analysis
    label: "Analysis"
    order: 2
    members:
      - 02_analysis/02_scripts/01_model.do

  - id: pipeline
    label: "Full Pipeline"
    member_cluster_ids: [data_prep, analysis]   # meta-cluster — no members here
```

**Step 4 — Validate**

```bash
.venv/Scripts/data-pipeline-flow render-image \
  --project-root <project_root> \
  --config <config_path> \
  --format png \
  --output <project_root>/viewer_output/_cluster_check.png
```

- [ ] Command exits without error
- [ ] No `cluster_member_not_found` or `unknown_cluster_id` diagnostics
- [ ] Cluster boxes appear with expected labels
- [ ] Meta-cluster nesting is visible

If a member is not found, the path is wrong — check it against node IDs in `summary` output.

**Step 5 — Report**

State which clusters were added or changed, the strategy in effect, and the render output path.


---

## Gotchas

- **`members` and `member_cluster_ids` are mutually exclusive.** A single entry
  cannot have both. Use `member_cluster_ids` for meta-clusters, `members` for leaves.

- **Paths must be project-relative.** Absolute paths or paths starting with `./`
  will not match any node and are silently ignored. Use node IDs from `summary` output.

- **`strategy: manual` hides everything not listed.** Nodes not in an explicit
  cluster disappear from all cluster boxes with no warning. Only use `manual`
  when you intend to define every cluster explicitly.

- **`lanes` field is removed.** Do not use it — it was deleted from the schema.

- **Two nesting levels maximum.** Meta-cluster → leaf cluster → files. Three
  levels are not supported.
