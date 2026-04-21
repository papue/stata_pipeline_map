from __future__ import annotations

from pathlib import Path

from stata_pipeline_flow.cli.main import _find_dot_executable, main
from stata_pipeline_flow.wizard import default_config_payload, update_exclusions_list, upsert_cluster


def test_cli_main_accepts_explicit_argv(tmp_path):
    dot_path = tmp_path / 'graph.dot'
    status = main(['render-dot', '--project-root', 'example/project', '--output', str(dot_path)])
    assert status == 0
    assert dot_path.exists()


def test_update_exclusions_list_add_and_remove():
    config = default_config_payload()
    update_exclusions_list(config, 'paths', 'old_versions')
    update_exclusions_list(config, 'folder_names', 'archive')
    assert 'old_versions' in config['exclusions']['paths']
    assert 'archive' in config['exclusions']['folder_names']
    update_exclusions_list(config, 'paths', 'old_versions', remove=True)
    assert 'old_versions' not in config['exclusions']['paths']


def test_upsert_cluster_replaces_existing_cluster():
    config = default_config_payload()
    upsert_cluster(config, 'analysis', 'Analysis', ['a.do'])
    upsert_cluster(config, 'analysis', 'Analysis new', ['b.do', 'folder/sub.do'], order=2)
    assert len(config['clusters']) == 1
    cluster = config['clusters'][0]
    assert cluster['id'] == 'analysis'
    assert cluster['label'] == 'Analysis new'
    assert cluster['members'] == ['b.do', 'folder/sub.do']
    assert cluster['order'] == 2


def test_find_dot_executable_respects_graphviz_dot_env(monkeypatch, tmp_path):
    fake_dot = tmp_path / 'dot.exe'
    fake_dot.write_text('echo dot', encoding='utf-8')
    monkeypatch.setenv('GRAPHVIZ_DOT', str(fake_dot))
    monkeypatch.setattr('shutil.which', lambda name: None)
    assert _find_dot_executable() == str(fake_dot)
