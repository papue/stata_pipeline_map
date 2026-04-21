from pathlib import Path

from data_pipeline_flow.wizard import normalize_config_destination, portable_path, resolve_user_path


def test_normalize_config_destination_appends_filename_for_directory(tmp_path: Path):
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    target_dir = repo_root / 'example'
    target_dir.mkdir()

    resolved = normalize_config_destination(str(target_dir), repo_root)

    assert resolved == target_dir / 'project_config.yaml'


def test_normalize_config_destination_keeps_yaml_filename(tmp_path: Path):
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()

    resolved = normalize_config_destination('configs/custom.yaml', repo_root)

    assert resolved == (repo_root / 'configs/custom.yaml').resolve()


def test_resolve_user_path_accepts_absolute_path(tmp_path: Path):
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    absolute = tmp_path / 'outside' / 'project'

    assert resolve_user_path(str(absolute), repo_root) == absolute


def test_portable_path_prefers_relative_inside_repo(tmp_path: Path):
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    inner = repo_root / 'example' / 'project'
    inner.mkdir(parents=True)

    assert portable_path(inner, repo_root) == 'example/project'


def test_portable_path_keeps_absolute_outside_repo(tmp_path: Path):
    repo_root = tmp_path / 'repo'
    repo_root.mkdir()
    outside = tmp_path / 'external' / 'project'
    outside.mkdir(parents=True)

    assert portable_path(outside, repo_root).endswith('/external/project')
