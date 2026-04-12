# stata-pipeline-flow

`stata-pipeline-flow` helps you understand a Stata project.

It scans your `.do` files and builds a pipeline map:
- which scripts exist
- which files they read
- which files they write
- where scripts depend on each other
- where the pipeline may be messy or suspicious

This repo already includes a **runnable example project** so you can try the tool immediately.

## What this tool is for

Use it when you want to answer questions like:
- "What is the structure of this Stata project?"
- "Which script creates this dataset?"
- "Which scripts write the same file?"
- "Which files are missing or only referenced?"
- "Can I generate a pipeline figure for documentation or discussion?"

## Before you start

You need:
- **Python 3.10 or newer**
- optionally **Graphviz** if you want PNG, SVG, or PDF output

Graphviz is only needed for final images. The tool itself can still create `.dot` graph files without it.

## Repository structure

These are the folders most users care about first:

- `src/` → the actual Python package
- `tests/` → automated tests
- `example/project/` → fake Stata project you can scan immediately
- `example/configs/` → example config file you can copy and edit
- `example/output/` → suggested place for generated output
- `docs/` → more detailed documentation for later

If you are new, start with `example/`.

---

## Easiest way to use this project

If you do not want to remember CLI commands, use the helper scripts in the repository root.
They ask questions, explain the available values, and save your choices so you do not need to repeat them every time.

The main helper scripts are:

- `python setup_project.py` -> first-run setup; choose project root, output folder, theme, view, and default format
  - during setup you can paste repo-relative paths or absolute paths; for the config location, giving a folder is allowed and `project_config.yaml` will be created inside it
- `python make_pipeline.py` -> create the pipeline figure using your saved defaults
- `python inspect_pipeline.py` -> run `summary`, `validate`, or both
- `python edit_exclusions.py` -> add or remove ignored files, folders, and glob patterns
- `python manage_clusters.py` -> add, edit, or delete manual clusters

The helper scripts call the same underlying engine as the CLI, but they are meant to be the friendlier starting point.

They save their remembered choices in:

```text
pipeline_user_settings.yaml
```

And by default they create the editable config here:

```text
user_configs/project_config.yaml
```

You can still change answers later. The scripts will show the saved values first and let you keep or replace them.

---

## Recommended beginner workflow

### Windows PowerShell

```powershell
cd "D:\path\to\pubrepo"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python setup_project.py
python make_pipeline.py
```

### macOS / Linux

```bash
cd /path/to/pubrepo
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python setup_project.py
python make_pipeline.py
```

If you prefer the direct CLI, it is still available, but the helper scripts are now the recommended path for normal use.

---

## 5-minute quick start

### Windows PowerShell

```powershell
cd "D:\path\to\pubrepo"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
stata-pipeline-flow summary --project-root example/project
```

If PowerShell blocks activation, run this once in the current terminal and then activate again:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
```

### macOS / Linux

```bash
cd /path/to/pubrepo
python3 -m venv .venv
. .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
stata-pipeline-flow summary --project-root example/project
```

If the `summary` command works, the installation is fine.

---

## The fastest useful workflow

### 1. Get a quick text overview

```bash
stata-pipeline-flow summary --project-root example/project
```

Use `summary` when you want a quick terminal overview.

It tells you:
- how many scripts and artifacts were found
- how many edges exist in the pipeline
- how many clusters were inferred
- which diagnostics were raised

### 2. Create a graph file

```bash
stata-pipeline-flow render-dot --project-root example/project --output example/output/pipeline_overview.dot
```

Use `render-dot` when you want the intermediate Graphviz `.dot` file.

A `.dot` file is a graph description. It is useful when:
- you want full control over later rendering
- you want to inspect the graph source
- you want to render with Graphviz manually

### 3. Create a final image directly

```bash
stata-pipeline-flow render-image --project-root example/project --format png --output example/output/pipeline_overview.png
```

Use `render-image` when you want the final figure directly from the CLI.

Supported formats:
- `png`
- `svg`
- `pdf`

If you also want to keep the `.dot` file:

```bash
stata-pipeline-flow render-image \
  --project-root example/project \
  --format svg \
  --output example/output/pipeline_overview.svg \
  --dot-output example/output/pipeline_overview.dot
```

### 4. Write a validation report

```bash
stata-pipeline-flow validate --project-root example/project --output example/output/validation_report.json
```

Use `validate` when you want a structured machine-readable diagnostics report.

### 5. Run the automated tests

```bash
python -m pytest -q
```

Use this when you are changing code and want to check that nothing broke.

---

## What the main commands mean

### `summary`
Prints a human-readable overview in the terminal.

### `render-dot`
Creates a `.dot` graph file.

### `render-image`
Creates a final image directly through Graphviz.

### `validate`
Writes a JSON report of diagnostics and validation findings.

### `extract-edges`
Writes a CSV of parsed edges from the Stata scripts.

### `snapshot-json`
Writes a stable JSON snapshot of the graph model itself.

### `export-clusters`
Exports inferred or resolved clusters as an editable YAML starter config.

---

## The example project: what to expect

The bundled example is **not a perfectly clean toy project**.
It is closer to a **realistic demo project** and intentionally includes some situations that produce diagnostics.

That means it is normal to see things like:
- missing referenced files
- multiple writers to the same target
- temporary files that get erased
- excluded files or folders

So if you run `summary` and see warnings, that does **not** automatically mean the tool is failing.
It often means the example is demonstrating what the tool can detect.

---

## Where to change settings

The easiest place to start is:

```text
example/configs/config_example.yaml
```

Run commands with that config like this:

```bash
stata-pipeline-flow render-image \
  --project-root example/project \
  --config example/configs/config_example.yaml \
  --format svg \
  --output example/output/pipeline_custom.svg
```

## The most important settings for a normal user

### `display.view`
Controls **what kind of graph** you see.

Common values:
- `overview` → the normal default view
- `scripts_only` → only scripts, no artifact nodes
- `deliverables` → focus on key outputs
- `stage_overview` → more compressed stage-style summary

### `display.theme`
Controls the visual style.

Available themes in this repo:
- `modern-light`
- `modern-dark`
- `warm-neutral`

### `display.label_path_depth`
Controls how much folder context is shown in node labels.

Examples:
- `0` → just the file name
- `1` → one parent folder plus the file name
- `2` → two parent folders plus the file name

This is useful when names repeat across folders.

### `display.show_extensions`
Controls whether labels keep extensions like `.do` or `.dta`.

### `display.node_label_style`
Controls the label style.

Common values:
- `basename` → file name only
- `full_path` → full relative path
- `stem` → file name without extension

### `exclusions.presets`
Turns on built-in exclusion groups.

In the example config these remove common clutter such as generated outputs, archival folders, and Python runtime noise.

### `exclusions.paths`, `folder_names`, `globs`
Use these to ignore folders or files you do not want in the graph.

### `parser.version_families`
Controls how file versions like `_v1`, `_v2`, `_qc`, `_pp`, or `final` are handled.

This matters when many file variants belong to the same logical output.

### `clustering`
Controls automatic grouping of the pipeline.

### `clusters`
Lets you manually override cluster membership.

---

## A very common beginner workflow

1. run `summary`
2. run `render-image` to create a PNG or SVG
3. inspect the figure
4. if the graph is too busy, edit `example/configs/config_example.yaml`
5. rerun the same command
6. once happy, use the same process on your real project

---


## PNG / SVG export and Graphviz

The tool can create image files such as PNG, SVG, and PDF through the `render-image` command.

Example:

```powershell
stata-pipeline-flow render-image --project-root example/project --format png --output example/output/pipeline_overview.png
```

This command needs **Graphviz** to be installed, because the actual image rendering uses Graphviz's `dot` program behind the scenes.

### Windows: check whether Graphviz is available

In PowerShell, test this first:

```powershell
where.exe dot
dot -V
```

If both commands work, then `render-image` should work too.

### Windows: common problem

A very common Windows issue is:

```text
Graphviz was not found on PATH. Install Graphviz and make sure the "dot" command works in your terminal.
```

This usually means one of these is true:
- Graphviz is not installed yet
- Graphviz is installed, but its `bin` folder is not on your PATH
- Graphviz was just installed, but you did not open a new PowerShell window yet

### Windows: quick fix for the current PowerShell session

If Graphviz is installed in the default location, run:

```powershell
$env:Path += ";C:\Program Files\Graphviz\bin"
where.exe dot
dot -V
```

Then retry:

```powershell
stata-pipeline-flow render-image --project-root example/project --format png --output example/output/pipeline_overview.png
```

### Windows: permanent fix

Add this folder to your Windows PATH:

```text
C:\Program Files\Graphviz\bin
```

Then:
1. close PowerShell
2. open a new PowerShell window
3. reactivate your virtual environment
4. rerun the command

### If you want to bypass PATH entirely

You can still create the DOT file and render it manually with the full Graphviz path:

```powershell
stata-pipeline-flow render-dot --project-root example/project --output example/output/pipeline_overview.dot
& "C:\Program Files\Graphviz\bin\dot.exe" -Tpng "D:\Sciebo New\stata_pipeline\pubrepo\example\output\pipeline_overview.dot" -o "D:\Sciebo New\stata_pipeline\pubrepo\example\output\pipeline_overview.png"
```

### If you do not want image export yet

You can always generate the `.dot` file first:

```powershell
stata-pipeline-flow render-dot --project-root example/project --output example/output/pipeline_overview.dot
```

A `.dot` file is the graph description. It is useful for checking the graph structure even before you render a final image.

## Troubleshooting

### PowerShell says `.venv/bin/activate` does not exist
You are using the Linux/macOS activation path on Windows.

Use:

```powershell
.\.venv\Scripts\Activate.ps1
```

### `Package requires a different Python: 3.9.x not in >=3.10`
Your virtual environment was created with too old a Python.

Delete `.venv` and recreate it with Python 3.10+.
For example:

```powershell
Remove-Item -Recurse -Force .venv
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### `dot` is not recognized
Graphviz is not installed or not on your PATH.

You now have two options:
- install/fix Graphviz and use `render-image`
- or use `render-dot` first and render later once Graphviz works

On Windows, Graphviz often installs to:

```text
C:\Program Files\Graphviz\bin
```

That folder must be on PATH if you want `dot` to work directly.

### `can't open example/output/...dot: No such file or directory`
You are probably running the command from the wrong folder.

Run commands from the **repo root** (`pubrepo`) or use absolute paths.

### The example prints many warnings
That is expected. The bundled example intentionally contains realistic diagnostics.

---

## Development notes

This repo is usable as a normal development repository.

Typical loop:

```bash
python -m pytest -q
stata-pipeline-flow summary --project-root example/project
stata-pipeline-flow render-image --project-root example/project --format svg --output example/output/dev_check.svg
```

If you want more detail after the README, continue with:
- `docs/configuration.md`
- `docs/development.md`
