# Interactive wrapper scripts

These scripts are the easiest way to operate the project if you do not want to remember CLI commands.

## Scripts

- `setup_project.py`: first-run setup and saved defaults
- `make_pipeline.py`: render a PNG, SVG, PDF, or DOT using saved defaults
- `inspect_pipeline.py`: run summary, validate, or both
- `edit_exclusions.py`: manage ignored paths, names, and glob patterns
- `manage_clusters.py`: manage manual clusters

## What gets remembered

Saved settings live in `pipeline_user_settings.yaml`.

By default, the main editable config lives in `user_configs/project_config.yaml`.

## Cluster entry style

When adding a cluster, enter one script path or folder path at a time.
Type `F` when you are finished.

This is meant to make multi-member clusters easy without forcing YAML edits for every small change.


## Path input rules

- You can enter repo-relative paths or absolute paths in the wrapper scripts.
- For the config location, you may give either a YAML file path or a folder path.
- If you give a folder, the wrapper creates `project_config.yaml` inside that folder automatically.
