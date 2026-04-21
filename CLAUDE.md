# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

`stata-pipeline-flow` is a Python tool that analyzes Stata research projects by scanning `.do` files to extract data lineage, building a dependency graph, and rendering pipeline visualizations (PNG/SVG/PDF via Graphviz) with built-in validation diagnostics.

## Setup and Installation

```bash
# Windows PowerShell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"

# macOS/Linux
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e ".[dev]"
```

Graphviz must be installed separately (and on PATH) for image output.

## Quick Example

Render the bundled example project (use the CLI entry point, not `python -m`):

```bash
# Windows
.venv\Scripts\stata-pipeline-flow render-image --project-root example/project --format png --output example/output/pipeline.png

# macOS/Linux
.venv/bin/stata-pipeline-flow render-image --project-root example/project --format png --output example/output/pipeline.png
```

Output: `example/output/pipeline.png`

## Commands

```bash
# Run all tests
python -m pytest -q

# Run a single test file
python -m pytest tests/test_smoke.py -q

# Run a specific test
python -m pytest tests/test_smoke.py::test_name -q

# CLI commands
stata-pipeline-flow summary --project-root example/project
stata-pipeline-flow render-image --project-root example/project --format png --output out.png
stata-pipeline-flow validate --project-root example/project --output report.json
stata-pipeline-flow render-dot --project-root example/project --output pipeline.dot
stata-pipeline-flow extract-edges --project-root example/project --output edges.csv
stata-pipeline-flow export-clusters --project-root example/project --output clusters.yaml
stata-pipeline-flow snapshot-json --project-root example/project --output graph.json
```

## Architecture

The pipeline executes in this order:

```
CLI (cli/main.py)
  → Config resolution (config/schema.py)
  → File discovery (parser/discovery.py)
  → Stata parsing (parser/stata_extract.py)  — regex-based, no AST
  → Graph model built (model/entities.py)
  → Rules applied in sequence:
      normalize.py      — standardize paths
      exclusions.py     — filter nodes/edges per config
      version_families.py — collapse _v1/_final variants
      clustering.py     — auto-infer logical groupings
      cluster_overrides.py — apply user-defined clusters
      layout.py         — graph arrangement hints
  → Validation (validation/diagnostics.py)
  → Rendering: dot.py / json_snapshot.py / edge_csv.py / config/export.py
```

### Key design points

- **Immutable dataclasses** for all entities: `Node`, `Edge`, `Cluster`, `Diagnostic`, `GraphModel` (model/entities.py)
- **Two-phase rendering**: full graph is built first; view filters (e.g. `scripts_only`, `show_data_nodes`) are applied at DOT generation time, not during graph construction
- **Stable node IDs** are project-relative normalized paths
- **Config** is YAML (`pipeline_user_settings.yaml` / `user_configs/project_config.yaml`); schema and defaults live in `config/schema.py`
- **Interactive wrapper scripts** (`setup_project.py`, `make_pipeline.py`, `inspect_pipeline.py`, `edit_exclusions.py`, `manage_clusters.py`) are thin wrappers around `cli/main.py` that prompt the user and persist settings to `pipeline_user_settings.yaml`

### Module map

| Module | Purpose |
|--------|---------|
| `cli/main.py` | CLI entry point (Click commands) |
| `config/schema.py` | Config dataclasses and defaults |
| `model/entities.py` | Core data model (GraphModel, Node, Edge, …) |
| `parser/stata_extract.py` | Regex extraction of `use`, `save`, `do`, `import`, `export` from `.do` files |
| `parser/discovery.py` | Filesystem walk with exclusion filtering |
| `rules/pipeline.py` | Orchestrates the full rules sequence |
| `rules/clustering.py` | Automatic cluster inference from folder/name patterns |
| `validation/diagnostics.py` | Missing files, duplicate writers, absolute paths, orphans |
| `render/dot.py` | Graphviz DOT generation |
| `wizard.py` | Interactive first-run setup wizard |

## Configuration

Config options are documented in `docs/configuration.md`. The schema with all defaults is in `config/schema.py`. Invalid config values fall back to sensible defaults rather than erroring.

## Testing

Tests are organized by development phase (`test_phase2_*` through `test_phase17_*`). Fixtures for regression tests live in `tests/fixtures/regression_project/`. Archived tests are in `tests/~old/` and should not be run.
