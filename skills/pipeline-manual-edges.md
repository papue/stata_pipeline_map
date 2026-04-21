---
name: pipeline-manual-edges
description: >
  Adds a manual edge to a data-pipeline-flow config when the parser misses a
  connection — macro-resolved paths, cross-language hand-offs (Stata/R/Python),
  or external inputs never on disk. Use when a graph link is missing, the
  pipeline flow is broken, or you need to inject an edge the parser cannot find.
  Does NOT handle cluster config, general rendering, or parser bug fixes.

allowed-tools: Bash, Read, Edit, Glob, Grep
---


## Goal

When the parser cannot statically extract a dependency, this skill identifies
the missing connection, locates the correct project-relative node IDs, writes a
`manual_edges` entry with a mandatory `note:`, and verifies the edge appears in
the pipeline. The result is an accurate graph without touching parser source code.

Not for: first-time installation (use pipeline-setup), general rendering (use
pipeline-inspect), cluster config (use pipeline-clusters), or fixing the parser
itself (requires source code changes).


---

## Routine

**venv path** — All CLI calls require the full venv path. Do not rely on PATH
activation (it doesn't persist across Bash calls). Use `.venv/Scripts/data-pipeline-flow`
on Windows or `.venv/bin/data-pipeline-flow` on macOS/Linux.

Run all CLI steps sequentially in the main agent — do not delegate to subagents.

**Step 1 — Locate the config**

Read the config (typically `pipeline_user_settings.yaml` or
`user_configs/project_config.yaml`). Check whether `manual_edges:` already
exists to avoid duplicates.

**Step 2 — List candidate node IDs**

```bash
.venv/Scripts/data-pipeline-flow extract-edges \
  --project-root <path> \
  --config <path> \
  --output <project-root>/viewer_output/_edges_check.csv
```

Read the CSV output. Node IDs are project-relative normalized paths — use them
verbatim as `source` and `target`. Ask the user to confirm the two endpoints if
either is absent from the CSV.

**Step 3 — Choose `on_missing` mode**

| Situation | Mode |
|-----------|------|
| Both nodes exist (or will exist) on disk | `warn` (default — safer) |
| Node is permanently undiscoverable (external DB, vendor file, another team's file) | `placeholder` |

Prefer `warn`. Use `placeholder` only for nodes that are genuinely unreachable
on disk — stale `placeholder` entries inject phantom nodes silently, with no
diagnostic to catch them.

**Step 4 — Write the config entry**

```yaml
manual_edges:
  - source: <project-relative/path/to/source>
    target: <project-relative/path/to/target>
    label: "<short visible label>"     # optional
    note: "<why the parser misses this>"
    on_missing: warn
```

Always include `note:` — without it, entries become unauditable after project restructuring.

**Step 5 — Verify**

```bash
.venv/Scripts/data-pipeline-flow summary \
  --project-root <path> \
  --config <path>
```

- [ ] Edge appears in the summary output
- [ ] No `manual_edge_node_not_found` diagnostic (when using `on_missing: warn`)
- [ ] No unexpected placeholder nodes

If `manual_edge_node_not_found` fires, the node ID in config does not match the
parser output — fix it by copying the ID verbatim from the edge CSV.

**Step 6 — Optionally re-render**

```bash
.venv/Scripts/data-pipeline-flow render-image --project-root <path> --config <path> --format png --output <out>
```


---

## Gotchas

- **`--config` is not auto-discovered.** Always pass it explicitly. Without it,
  the manual edges are never read and appear to have no effect.

- **Node IDs must be exact.** Copy them verbatim from the edge CSV. A single
  character difference silently skips the edge or fires `manual_edge_node_not_found`.

- **`on_missing: placeholder` goes stale silently.** If the referenced file is
  later moved or renamed, the phantom node remains with no warning. Reserve
  `placeholder` for permanently undiscoverable nodes.

- **Always add `note:`.** After any project restructuring, entries without a
  note are impossible to audit. Make it a hard rule.
