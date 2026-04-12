# Migration notes

This project has grown from a small DOT renderer into a configurable lineage tool with semantic artifact roles, display presets, and layout controls.

## Safe upgrade path

Existing configs continue to work.

Behavior changes worth noticing:

- terminal deliverables such as `.csv`, `.xlsx`, `.pdf`, `.png`, and `.ster` are shown by default
- temporary artifacts remain hidden by default
- loop-generated outputs can now appear either as concrete artifact nodes or as placeholder nodes
- likely version-family files can emit diagnostics even when graph semantics stay literal

## New commands

- `snapshot-json` writes a stable JSON graph snapshot for downstream tooling and regression checks

## New config areas

### Display

Useful additions:

- `display.label_path_depth`
- `display.show_extensions`
- `display.node_label_style`
- `display.view`
- `display.theme`
- `display.show_terminal_outputs`
- `display.show_temporary_outputs`
- `display.placeholder_style`
- `display.edge_label_mode`

### Parser

Useful additions:

- `parser.dynamic_paths.mode`
- `parser.dynamic_paths.placeholder_token`
- `parser.version_families.mode`
- `parser.version_families.priority_suffixes`
- `parser.version_families.tiebreaker`

### Layout and clusters

Useful additions:

- `layout.rankdir`
- `layout.cluster_lanes`
- `layout.unclustered_artifacts_position`
- `clusters[].lane`
- `clusters[].order`
- `clusters[].collapse`

## Invalid values

Invalid values do not stop the run.

The current behavior is:

- unsupported display presets fall back to documented defaults
- negative label path depth falls back to `0`
- unsupported dynamic-path and version-family modes fall back to conservative defaults
- invalid layout values warn and fall back safely

## Recommended migration flow

1. keep your old config and run `summary`
2. run `validate`
3. inspect `snapshot-json` if you need a machine-readable export
4. add only the new settings you actually care about
5. use `docs/examples/minimal_config.yaml` or `docs/examples/advanced_config.yaml` as a starting point
