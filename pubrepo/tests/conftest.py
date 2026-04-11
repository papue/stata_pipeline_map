from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess
import sys

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REGRESSION_FIXTURE_ROOT = PROJECT_ROOT / 'tests' / 'fixtures' / 'regression_project'
GOLDEN_ROOT = REGRESSION_FIXTURE_ROOT / 'golden'
FIXTURE_PROJECT_TEMPLATE = PROJECT_ROOT / 'tests' / '~old' / 'regression_project' / 'stata_regression_project'


@pytest.fixture()
def regression_project_root(tmp_path: Path) -> Path:
    destination = tmp_path / FIXTURE_PROJECT_TEMPLATE.name
    shutil.copytree(FIXTURE_PROJECT_TEMPLATE, destination)
    return destination


def run_cli(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / 'run_phase1_cli.py'), *args],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def read_text(path: Path) -> str:
    return path.read_text(encoding='utf-8').replace('\r\n', '\n').rstrip('\n')


def read_json(path: Path) -> object:
    return json.loads(read_text(path))


def normalize_project_root_text(text: str, project_root: Path) -> str:
    return text.replace('\r\n', '\n').replace(str(project_root), '<PROJECT_ROOT>').rstrip('\n')
