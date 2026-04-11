from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import stata_pipeline_flow.cli.main as cli_main


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')


def test_render_image_command_returns_clear_message_when_graphviz_missing(tmp_path: Path, monkeypatch, capsys) -> None:
    project_root = tmp_path / 'project'
    _write(project_root / 'main.do', 'save "work/panel.dta", replace\n')
    output_path = tmp_path / 'graph.png'

    monkeypatch.setattr(cli_main.shutil, 'which', lambda name: None)

    args = SimpleNamespace(
        project_root=str(project_root),
        config=None,
        edge_csv='viewer_output/parser_edges.csv',
        show_edge_labels=False,
        output=str(output_path),
        format='png',
        dot_output=None,
    )

    code = cli_main.command_render_image(args)
    captured = capsys.readouterr()

    assert code == 2
    assert 'Graphviz was not found on PATH' in captured.out
    assert not output_path.exists()


def test_render_image_command_writes_image_and_optional_dot(tmp_path: Path, monkeypatch) -> None:
    project_root = tmp_path / 'project'
    _write(project_root / 'main.do', 'save "work/panel.dta", replace\n')
    output_path = tmp_path / 'graph.svg'
    dot_output = tmp_path / 'graph.dot'

    monkeypatch.setattr(cli_main.shutil, 'which', lambda name: '/usr/bin/dot')

    def fake_run(cmd, input, text, capture_output, check):
        assert cmd == ['/usr/bin/dot', '-Tsvg', '-o', str(output_path)]
        assert 'digraph pipeline {' in input
        output_path.write_text('<svg></svg>', encoding='utf-8')
        return SimpleNamespace(returncode=0, stderr='')

    monkeypatch.setattr(cli_main.subprocess, 'run', fake_run)

    args = SimpleNamespace(
        project_root=str(project_root),
        config=None,
        edge_csv='viewer_output/parser_edges.csv',
        show_edge_labels=False,
        output=str(output_path),
        format='svg',
        dot_output=str(dot_output),
    )

    code = cli_main.command_render_image(args)

    assert code == 0
    assert output_path.read_text(encoding='utf-8') == '<svg></svg>'
    assert 'digraph pipeline {' in dot_output.read_text(encoding='utf-8')
