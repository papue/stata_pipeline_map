# data-pipeline-flow

`data-pipeline-flow` maps a research project's data pipeline from `.do`, `.py`, and `.R` scripts. It shows which scripts read and write which files, where scripts depend on each other, and where the pipeline may be messy or suspicious.

It is designed for quickly answering questions like:

- Which script creates this dataset?
- Which scripts write the same file?
- Where are the missing or suspicious links in the pipeline?
- Can I generate a figure of the pipeline for documentation or discussion?

## Installation

Requirements:

- Python 3.10+
- Graphviz only if you want PNG, SVG, or PDF output

From the repository root:

```bash
python install.py
```

This creates a virtual environment, installs the package, checks for Graphviz, and runs a smoke test on the bundled example project.

Activate the environment for your session:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

## First use

The fastest path is:

```bash
data-pipeline-flow-setup
data-pipeline-flow-make
```

The setup helper saves your default choices, and the make helper rebuilds the figure from those saved settings.

## Main commands

Use the direct CLI when you want full control:

| Command | Purpose |
|---|---|
| `data-pipeline-flow summary --project-root <path>` | Print a quick terminal overview |
| `data-pipeline-flow render-dot --project-root <path> --output <file.dot>` | Write the Graphviz `.dot` graph |
| `data-pipeline-flow render-image --project-root <path> --format <png|svg|pdf> --output <file>` | Render the final image |
| `data-pipeline-flow validate --project-root <path> --output <file.json>` | Write a validation report |
| `data-pipeline-flow extract-edges --project-root <path> --output <file.csv>` | Export parsed pipeline edges |
| `data-pipeline-flow snapshot-json --project-root <path> --output <file.json>` | Export a graph snapshot |
| `data-pipeline-flow export-clusters --project-root <path> --output <file.yaml>` | Export inferred or resolved clusters |

Interactive helpers are also installed:

| Helper | Purpose |
|---|---|
| `data-pipeline-flow-setup` | First-run setup for project root, output folder, theme, view, and format |
| `data-pipeline-flow-make` | Render using saved defaults |
| `data-pipeline-flow-inspect` | Run `summary`, `validate`, or both |
| `data-pipeline-flow-edit-exclusions` | Edit ignored files, folders, and patterns |
| `data-pipeline-flow-manage-clusters` | Edit manual clusters |

Saved settings are stored in `pipeline_user_settings.yaml`. The editable project config is created by default at `user_configs/project_config.yaml`.

## Example workflow

The repository includes a runnable example project. From the repo root:

```bash
# 1) check that the install worked
data-pipeline-flow summary --project-root example/project

# 2) create a pipeline image
data-pipeline-flow render-image \
  --project-root example/project \
  --format svg \
  --output example/output/pipeline_overview.svg

# 3) optionally keep the intermediate DOT file too
data-pipeline-flow render-image \
  --project-root example/project \
  --format svg \
  --output example/output/pipeline_overview.svg \
  --dot-output example/output/pipeline_overview.dot
```

The example is intentionally realistic rather than perfectly clean. Warnings such as missing referenced files or multiple writers can be expected and often demonstrate what the tool is designed to detect.

## Configuration

Start from:

```text
example/configs/config_example.yaml
```

Common settings most users will care about first:

- `display.view`: choose the graph view such as `overview`, `scripts_only`, `deliverables`, or `stage_overview`
- `display.theme`: choose the visual style such as `modern-light`, `modern-dark`, or `warm-neutral`
- `display.label_path_depth`: control how much folder context appears in labels
- `exclusions.*`: ignore clutter such as generated folders, archive folders, or glob patterns
- `parser.version_families`: control how file versions such as `_v1`, `_qc`, `_pp`, or `final` are handled
- `clustering` / `clusters`: control automatic grouping and manual cluster overrides

Example:

```bash
data-pipeline-flow render-image \
  --project-root example/project \
  --config example/configs/config_example.yaml \
  --format svg \
  --output example/output/pipeline_custom.svg
```

## Repository layout

```text
src/                 Python package
example/project/     bundled demo project
example/configs/     example configuration
example/output/      suggested output location
tests/               automated tests
docs/                additional documentation
```

## Notes

- Multi-language parsing for Stata, Python, and R is enabled by default.
- If Graphviz is not available, you can still generate `.dot` files with `render-dot`.
- For development checks, run `python -m pytest -q`.

## Troubleshooting

### `dot` is not recognized

Graphviz is missing or not on your PATH. You can either install/fix Graphviz and use `render-image`, or use `render-dot` first and render later.

### PowerShell activation fails

Use:

```powershell
.\.venv\Scripts\Activate.ps1
```

If needed, run once in the current session:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```
