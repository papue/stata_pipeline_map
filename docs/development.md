# Development notes

This document is the maintainer-oriented companion to the README.

## Architecture at a glance

The main execution flow is:

1. CLI resolves config and runtime overrides.
2. Project discovery walks the repository and applies exclusions.
3. The parser reads `.do` files directly and extracts script calls, reads, writes, and erase events.
4. A graph model is built with project-relative node ids.
5. Automatic clustering runs if enabled.
6. Manual cluster overrides run if configured.
7. Validation diagnostics are added.
8. The graph is rendered or exported depending on the command.

## Important modules

### CLI

- `src/data_pipeline_flow/cli/main.py`

Owns argument parsing and command entrypoints.

### Config

- `src/data_pipeline_flow/config/schema.py`
- `src/data_pipeline_flow/config/export.py`

`schema.py` defines the config dataclasses and loader.

`export.py` writes editable cluster YAML using current graph cluster membership.

### Discovery and parsing

- `src/data_pipeline_flow/parser/discovery.py`
- `src/data_pipeline_flow/parser/stata_extract.py`
- `src/data_pipeline_flow/parser/edge_csv.py`

`discovery.py` decides which files belong to the project scan.

`stata_extract.py` does the direct `.do` parsing. This is where command recognition, absolute-path diagnostics, excluded-reference diagnostics, artifact classification, and edge extraction live.

### Graph model and normalization

- `src/data_pipeline_flow/model/entities.py`
- `src/data_pipeline_flow/model/normalize.py`

The graph model is intentionally simple and serializable.

Project-relative normalized paths are the stable node ids used across clustering, validation, exports, and regression tests.

### Rules layer

- `src/data_pipeline_flow/rules/pipeline.py`
- `src/data_pipeline_flow/rules/exclusions.py`
- `src/data_pipeline_flow/rules/clustering.py`
- `src/data_pipeline_flow/rules/cluster_overrides.py`

`pipeline.py` is the orchestration layer.

`clustering.py` contains the deterministic automatic clustering logic.

`cluster_overrides.py` applies manual clusters on top and recomputes artifact cluster assignments.

### Rendering and validation

- `src/data_pipeline_flow/render/dot.py`
- `src/data_pipeline_flow/validation/diagnostics.py`

`render/dot.py` is intentionally lightweight. Keep rendering concerns separate from graph-building concerns.

`validation/diagnostics.py` is where graph-level consistency checks live.

## Extension guidance

### Adding parser support for another Stata command

The safest place is usually `parser/stata_extract.py`.

Typical checklist:

1. add a regex for the command
2. decide whether it is a read, write, script-call, or diagnostic-only event
3. normalize its path through the existing normalization utilities
4. respect exclusions before adding graph entities
5. add targeted tests
6. update regression fixtures only if output behavior intentionally changes

### Changing clustering behavior

Be careful here.

Clustering is now part of the user-facing behavior and also covered by regression tests. Changes in:

- cluster ids
- cluster labels
- cluster membership
- export ordering

can all cascade into golden diffs.

### Changing output formatting

Also be careful.

Regression-style protection currently covers:

- graph semantics
- edge CSV
- DOT rendering
- validation report
- cluster export
- summary CLI output

Do not reformat output-producing code casually.

## Testing strategy

The suite currently mixes focused tests and realistic regression checks.

### Focused tests

Files such as these cover individual capabilities:

- `tests/test_phase2_normalization.py`
- `tests/test_phase3_validation.py`
- `tests/test_phase5_clustering.py`
- `tests/test_phase6_manual_clusters.py`
- `tests/test_phase7_cluster_export.py`
- `tests/test_phase8_manual_cluster_validation.py`
- `tests/test_phase9_regression.py`

### Regression fixture layout

The regression setup intentionally separates:

- **template project**: `tests/~old/regression_project/stata_regression_project/`
- **golden outputs**: `tests/fixtures/regression_project/golden/`

This separation matters.

The template project is under an excluded path (`~old`) so the real repository-root scan does not accidentally pull its `.do` files into normal CLI runs.

Do not move fixture `.do` files into non-excluded scanned folders unless you deliberately want repository-root outputs to change.

### Helper organization

Keep shared test helpers in `tests/conftest.py` or in clearly non-test helper modules.

Avoid creating helper files whose names look like test modules unless you want `pytest` to collect them.

### Running the suite

From the project root:

```bash
PYTHONPATH=src pytest -q
```

Useful targeted runs:

```bash
PYTHONPATH=src pytest -q tests/test_phase9_regression.py
PYTHONPATH=src pytest -q tests/test_phase8_manual_cluster_validation.py
```

## Golden update discipline

When a deliberate behavior change is made, update goldens only after confirming the new behavior is wanted.

A sensible sequence is:

1. run the targeted CLI commands on the regression fixture
2. inspect the output diff manually
3. update golden files only for intentional changes
4. rerun the full test suite

If a change was only for documentation, the golden files should not need to move.

## Current command contract

The current CLI commands are:

- `summary`
- `extract-edges`
- `render-dot`
- `validate`
- `export-clusters`

If you add a new command later, update:

- `README.md`
- `docs/configuration.md` if config surface changes
- regression or integration coverage as appropriate

## CLI entrypoints

The preferred lightweight runner in this public bundle is `run_cli.py`.

The installable console script remains `data-pipeline-flow`.
