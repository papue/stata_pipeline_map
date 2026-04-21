# Example folder

This folder exists so you can try the tool immediately without preparing your own project first.

## What each subfolder means

### `project/`
A fake but realistic Stata project.

This is the folder the CLI scans in all example commands.

### `configs/`
Example config files.

Start with:

```text
example/configs/config_example.yaml
```

### `output/`
A suggested place for generated files such as:
- `.dot` graph files
- `.png`, `.svg`, or `.pdf` images
- validation reports
- exported cluster YAML

Keeping outputs here avoids cluttering the repo root.

## Fastest commands to try

From the repository root:

```bash
data-pipeline-flow summary --project-root example/project
data-pipeline-flow render-image --project-root example/project --format png --output example/output/pipeline_overview.png
data-pipeline-flow validate --project-root example/project --output example/output/validation_report.json
```

If Graphviz is not installed yet, use this instead for the figure step:

```bash
data-pipeline-flow render-dot --project-root example/project --output example/output/pipeline_overview.dot
```

## What to expect from the example

The example project is intentionally not perfectly clean.
It includes some realistic pipeline problems so you can see the diagnostics system doing something useful.

So warnings in the example are normal.

## When to edit the config

Edit the config when you want to:
- change the theme
- simplify labels
- hide clutter
- change the view
- ignore old folders or temp files
- guide clustering manually

Then rerun, for example:

```bash
data-pipeline-flow render-image \
  --project-root example/project \
  --config example/configs/config_example.yaml \
  --format svg \
  --output example/output/pipeline_custom.svg
```

## Rendering a PNG or SVG

If you want a final image instead of only a `.dot` file, use:

```powershell
data-pipeline-flow render-image --project-root example/project --format png --output example/output/pipeline_overview.png
```

On Windows, this needs Graphviz and the `dot` command must work in PowerShell.

Quick check:

```powershell
where.exe dot
dot -V
```

If that fails but Graphviz is installed in the default folder, use this temporary session fix:

```powershell
$env:Path += ";C:\Program Files\Graphviz\bin"
```


## Friendlier wrapper scripts

If you do not want to remember the CLI syntax, use these from the repository root:

```text
python setup_project.py
python make_pipeline.py
python inspect_pipeline.py
python edit_exclusions.py
python manage_clusters.py
```

These scripts ask questions, explain the valid values, and save your defaults so you do not need to answer everything each time.
