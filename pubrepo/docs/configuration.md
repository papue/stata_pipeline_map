# Configuration reference

This file explains the config options in more detail.

If you are new to the tool, do **not** start here.
Start with the main `README.md` first, then open `example/configs/config_example.yaml`, then return here only for details.

A simple mental model:
- `display` = how the graph should look
- `exclusions` = what should be ignored
- `parser` = how paths and versions are interpreted
- `clusters` = manual grouping of related scripts
- `layout` = overall graph arrangement

This document describes the current config surface.

## Safe fallback rule

For all settings below:

- missing value -> use the default
- invalid value -> fall back safely to the default
- invalid layout values additionally emit diagnostics in the graph

## Top-level sections

For everyday use, the most important sections are usually:

- `display` for graph style and focus
- `exclusions` for scan hygiene
- `parser.version_families` for `_v1` / `_QC` / `_final` families
- `clusters` for manual grouping on top of auto clustering
- `layout` for presentation polish


```yaml
project_root: .
display: {}
exclusions: {}
normalization: {}
parser: {}
classification: {}
clustering: {}
layout: {}
clusters: []
```

## `display`

### `theme`

Allowed values:

- `modern-light` (default)
- `modern-dark`
- `warm-neutral`

Invalid fallback: `modern-light`

### `view`

Allowed values:

- `overview` (default)
- `deliverables`
- `technical`
- `scripts_only`
- `stage_overview`

Invalid fallback: `overview`

### `label_path_depth`

Allowed values: integer `0+`

Default: `0`

Invalid fallback: `0`

### `show_extensions`

Allowed values: `true`, `false`

Default: `true`

Invalid fallback: `true`

### `node_label_style`

Allowed values:

- `basename` (default)
- `stem`
- `full_path`

Invalid fallback: `basename`

### `show_terminal_outputs`

Allowed values: `true`, `false`

Default: `true`

Invalid fallback: `true`

### `show_temporary_outputs`

Allowed values: `true`, `false`

Default: `false`

Invalid fallback: `false`

Behavior notes:
- when `false`, temporary outputs are omitted from the rendered graph and a diagnostic summary reports how many were hidden
- when `true`, temporary write artifacts are rendered, including temporary artifacts later erased in the same script
- in `deliverables`, `scripts_only`, and `stage_overview` views this setting does not visibly change the rendered nodes; the run emits an informational diagnostic so that this is explicit

### `placeholder_style`

Allowed values:

- `dashed` (default)
- `filled_dashed`
- `bold`

Invalid fallback: `dashed`

### `edge_label_mode`

Allowed values:

- `auto` (default)
- `hidden`
- `show`
- `operation`

Invalid fallback: `auto`

## `parser`

### `edge_csv_path`

Default: `viewer_output/parser_edges.csv`

### `prefer_existing_edge_csv`

Default: `false`

### `write_edge_csv`

Default: `true`

### `suppress_internal_only_writes`

Default: `true`

### `dynamic_paths.mode`

Allowed values:

- `literal_only`
- `resolve_simple` (default)
- `resolve_loops`
- `resolve_loops_with_placeholders`

Invalid fallback: `resolve_simple`

### `dynamic_paths.placeholder_token`

Default: `{dynamic}`

Invalid fallback: `{dynamic}`

### `version_families.mode`

Allowed values:

- `off`
- `detect_only` (default)
- `prefer_latest_modified`
- `prefer_highest_numeric`
- `prefer_priority_suffix`

Invalid fallback: `detect_only`

Behavior notes:
- `detect_only` emits diagnostics but keeps all literal artifact nodes
- `prefer_latest_modified` collapses a family to the existing member with the newest modified time
- `prefer_highest_numeric` prefers the highest `_v<number>` member when present
- `prefer_priority_suffix` prefers the earliest configured suffix in `priority_suffixes`

### `version_families.priority_suffixes`

Default: `[qc, pp, final, draft]`

### `version_families.tiebreaker`

Default: `latest_modified`

## `classification`

### `deliverable_extensions`

Default:

```yaml
[.csv, .xlsx, .pdf, .png, .svg, .docx, .tex, .ster]
```

### `temporary_name_patterns`

Default:

```yaml
[_tmp, _temp, _scratch, temp_, tmp_]
```

## `layout`

### `rankdir`

Allowed values:

- `LR` (default)
- `TB`

Invalid fallback: `LR`

### `cluster_lanes`

List of lane definitions:

```yaml
layout:
  cluster_lanes:
    - lane: main
      cluster_ids: [data_prep, analysis]
```

If a lane references a missing cluster, the run continues and a warning diagnostic is emitted.

### `unclustered_artifacts_position`

Allowed values:

- `auto` (default)
- `left`
- `right`
- `separate_lane`

Invalid fallback: `auto`

## `clusters`

Each entry accepts:

- `id` or `cluster_id`
- optional `label`
- `members`
- optional `lane`
- optional `order`
- optional `collapse`

Example:

```yaml
clusters:
  - id: analysis
    label: Analysis
    members:
      - 02_analysis/02_scripts/01_model.do
    lane: main
    order: 2
    collapse: false
```

## Example configs

- minimal: [`docs/examples/minimal_config.yaml`](examples/minimal_config.yaml)
- advanced: [`docs/examples/advanced_config.yaml`](examples/advanced_config.yaml)


## View-specific usability notes

Some display controls are intentionally view-specific.

- `deliverables` focuses on scripts plus deliverable/reference nodes. Temporary-output visibility settings do not materially change that view.
- `scripts_only` and `stage_overview` bridge through hidden artifacts, so terminal or temporary artifact toggles do not visibly change rendered nodes.
- `stage_overview` renders cluster summary nodes rather than artifact-level labels, so `node_label_style`, `label_path_depth`, and `show_extensions` do not visibly change labels there.

The CLI summary prints a `Config effects` block and the graph diagnostics include `display_option_irrelevant` entries when one of these cases applies.


## `exclusions`

This section is intentionally additive-friendly.

Recommended pattern:

```yaml
exclusions:
  presets:
    - generated_outputs
    - archival_folders
    - python_runtime
  globs:
    - '*.tmp'
  folder_names:
    - scratch
```

What the presets mean:

- `generated_outputs`: excludes generated render/output folders such as `viewer_output`
- `archival_folders`: excludes folders such as `archive`, `old`, `~old`, and `backup`
- `python_runtime`: excludes runtime noise such as `.git`, `__pycache__`, and `.pytest_cache`

Important behavior note:

- presets are not magically re-added if you remove them
- if `presets: []` and you only list custom exclusions, only those custom rules apply
- the CLI now prints an explicit note in that case so the behavior is visible during normal runs

Useful rule of thumb:

- want to *add one more thing* to the usual defaults -> keep the presets and add your custom rule
- want full manual control -> clear the presets on purpose and list everything you want excluded

### `presets`

Default:

```yaml
[generated_outputs, archival_folders, python_runtime]
```

### `paths`

Convenience list for exact file paths or folder prefixes.

Examples:

```yaml
paths:
  - viewer_output/
  - data/tmp_snapshot.csv
```

A trailing slash is treated as a folder/prefix exclusion.

### `file_names`

Convenience alias for exact file-name exclusions regardless of folder.

Example:

```yaml
file_names:
  - notes.txt
  - debug_copy.do
```
