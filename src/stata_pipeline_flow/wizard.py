from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore
except Exception as exc:  # pragma: no cover
    raise RuntimeError('PyYAML is required for the interactive helper scripts.') from exc

THEME_HELP = {
    'modern-light': 'bright default theme; easiest to read on white backgrounds',
    'modern-dark': 'dark background theme; useful for slides or dark viewers',
    'warm-neutral': 'softer beige/orange theme; more presentation-like',
}
VIEW_HELP = {
    'overview': 'best default; balanced graph with scripts and artifacts',
    'deliverables': 'focus on outputs and key deliverables; hides some clutter',
    'scripts_only': 'show only scripts; useful for structure without data files',
    'stage_overview': 'higher-level stage feeling; emphasizes grouped script flow',
    'technical': 'reserved/advanced mode; usually keep overview instead',
}
FORMAT_HELP = {
    'png': 'best for quick sharing in documents or chats',
    'svg': 'best quality for zooming and editing later',
    'pdf': 'good for print-style export',
    'dot': 'graph source only; useful for debugging or manual Graphviz rendering',
}
LABEL_STYLE_HELP = {
    'basename': 'show only the file name',
    'stem': 'show file name without extension',
    'full_path': 'show the whole project-relative path',
}
SETTINGS_FILENAME = 'pipeline_user_settings.yaml'
DEFAULT_CONFIG_RELATIVE = 'user_configs/project_config.yaml'
DEFAULT_OUTPUT_DIR = 'user_output'


def normalize_user_path(raw: str) -> str:
    return raw.strip().replace('\\', '/')


def resolve_user_path(value: str, repo_root: Path) -> Path:
    cleaned = normalize_user_path(value)
    candidate = Path(cleaned).expanduser()
    if candidate.is_absolute():
        return candidate
    return (repo_root / cleaned).resolve()


def portable_path(path: Path, repo_root: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo_root.resolve())).replace('\\', '/')
    except Exception:
        return str(path.resolve()).replace('\\', '/')


def normalize_config_destination(raw: str, repo_root: Path) -> Path:
    target = resolve_user_path(raw, repo_root)
    suffixes = {'.yaml', '.yml'}
    if target.exists() and target.is_dir():
        return target / 'project_config.yaml'
    if target.suffix.lower() in suffixes:
        return target
    if not target.suffix:
        return target / 'project_config.yaml' if not target.name.lower().endswith(('.yaml', '.yml')) else target
    return target


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _settings_path(repo_root: Path | None = None) -> Path:
    base = repo_root or _repo_root()
    return base / SETTINGS_FILENAME


def load_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return yaml.safe_load(path.read_text(encoding='utf-8')) or {}



def write_yaml_file(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True), encoding='utf-8')



def load_settings(repo_root: Path | None = None) -> dict[str, Any]:
    return load_yaml_file(_settings_path(repo_root))



def save_settings(settings: dict[str, Any], repo_root: Path | None = None) -> Path:
    path = _settings_path(repo_root)
    write_yaml_file(path, settings)
    return path



def default_config_payload(project_root: str = 'example/project') -> dict[str, Any]:
    return {
        'project_root': project_root,
        'display': {
            'show_edge_labels': False,
            'mode': 'overview',
            'theme': 'modern-light',
            'show_terminal_outputs': True,
            'show_temporary_outputs': False,
            'placeholder_style': 'dashed',
            'label_path_depth': 0,
            'show_extensions': True,
            'node_label_style': 'basename',
            'view': 'overview',
            'edge_label_mode': 'auto',
        },
        'exclusions': {
            'presets': ['generated_outputs', 'archival_folders', 'python_runtime'],
            'paths': [],
            'file_names': [],
            'exact_paths': [],
            'prefixes': [],
            'globs': ['*.tmp', '*.bak'],
            'exact_names': [],
            'folder_names': [],
        },
        'normalization': {
            'path_prefix_aliases': {},
            'project_root_markers': [],
            'strip_leading_dot': True,
        },
        'parser': {
            'edge_csv_path': 'viewer_output/parser_edges.csv',
            'prefer_existing_edge_csv': False,
            'write_edge_csv': True,
            'suppress_internal_only_writes': True,
            'dynamic_paths': {
                'mode': 'resolve_simple',
                'placeholder_token': '{dynamic}',
            },
            'version_families': {
                'mode': 'detect_only',
                'priority_suffixes': ['qc', 'pp', 'final', 'draft'],
                'tiebreaker': 'latest_modified',
            },
        },
        'classification': {
            'deliverable_extensions': ['.csv', '.xlsx', '.pdf', '.png', '.svg', '.docx', '.tex', '.ster'],
            'temporary_name_patterns': ['_tmp', '_temp', '_scratch', 'temp_', 'tmp_'],
        },
        'clustering': {
            'enabled': True,
            'strategy': 'auto',
        },
        'layout': {
            'rankdir': 'LR',
            'cluster_lanes': [],
            'unclustered_artifacts_position': 'auto',
        },
        'clusters': [],
    }



def load_or_create_config(config_path: Path, project_root: str = 'example/project') -> dict[str, Any]:
    if config_path.exists():
        config = load_yaml_file(config_path)
    else:
        config = default_config_payload(project_root=project_root)
    config.setdefault('project_root', project_root)
    config.setdefault('display', {})
    config['display'].setdefault('theme', 'modern-light')
    config['display'].setdefault('view', 'overview')
    config['display'].setdefault('node_label_style', 'basename')
    config['display'].setdefault('label_path_depth', 0)
    config.setdefault('exclusions', {})
    config['exclusions'].setdefault('presets', ['generated_outputs', 'archival_folders', 'python_runtime'])
    for key in ['paths', 'file_names', 'exact_paths', 'prefixes', 'globs', 'exact_names', 'folder_names']:
        config['exclusions'].setdefault(key, [])
    config.setdefault('clusters', [])
    config.setdefault('layout', {})
    config['layout'].setdefault('cluster_lanes', [])
    return config



def save_config(config_path: Path, config: dict[str, Any]) -> None:
    write_yaml_file(config_path, config)



def print_section(title: str) -> None:
    print(f'\n=== {title} ===')



def prompt_text(question: str, default: str | None = None, allow_empty: bool = False) -> str:
    suffix = f' [{default}]' if default not in (None, '') else ''
    while True:
        value = input(f'{question}{suffix}: ').strip()
        if value:
            return value
        if default is not None:
            return default
        if allow_empty:
            return ''
        print('Please enter a value. Press Enter only when a default is shown.')



def prompt_yes_no(question: str, default: bool = True) -> bool:
    hint = 'Y/n' if default else 'y/N'
    while True:
        value = input(f'{question} [{hint}]: ').strip().lower()
        if not value:
            return default
        if value in {'y', 'yes'}:
            return True
        if value in {'n', 'no'}:
            return False
        print('Please answer with y or n.')



def prompt_choice(question: str, choices: dict[str, str], default: str) -> str:
    print(question)
    for key, explanation in choices.items():
        marker = ' (default)' if key == default else ''
        print(f'  - {key}: {explanation}{marker}')
    while True:
        value = input(f'Choose one [{default}]: ').strip()
        if not value:
            return default
        if value in choices:
            return value
        print('That value is not valid. Pick one of the values listed above.')



def prompt_int(question: str, default: int) -> int:
    while True:
        value = input(f'{question} [{default}]: ').strip()
        if not value:
            return default
        try:
            parsed = int(value)
        except ValueError:
            print('Please enter a whole number.')
            continue
        if parsed < 0:
            print('Please enter 0 or a positive whole number.')
            continue
        return parsed



def ensure_relative(value: str) -> str:
    return normalize_user_path(value)



def update_display_settings(config: dict[str, Any], theme: str, view: str, label_style: str, label_depth: int, show_extensions: bool) -> None:
    display = config.setdefault('display', {})
    display['theme'] = theme
    display['view'] = view
    display['node_label_style'] = label_style
    display['label_path_depth'] = label_depth
    display['show_extensions'] = show_extensions



def update_exclusions_list(config: dict[str, Any], key: str, value: str, remove: bool = False) -> None:
    exclusions = config.setdefault('exclusions', {})
    items = exclusions.setdefault(key, [])
    cleaned = ensure_relative(value)
    if not cleaned:
        return
    if remove:
        exclusions[key] = [item for item in items if item != cleaned]
        return
    if cleaned not in items:
        items.append(cleaned)



def upsert_cluster(config: dict[str, Any], cluster_id: str, label: str | None, members: list[str], lane: str | None = None, order: int | None = None, collapse: bool = False) -> None:
    clusters = config.setdefault('clusters', [])
    payload = {
        'id': cluster_id,
        'label': label or cluster_id,
        'members': [ensure_relative(member) for member in members if ensure_relative(member)],
    }
    if lane:
        payload['lane'] = lane
    if order is not None:
        payload['order'] = int(order)
    if collapse:
        payload['collapse'] = True
    for index, cluster in enumerate(clusters):
        existing_id = str(cluster.get('id') or cluster.get('cluster_id') or '').strip()
        if existing_id == cluster_id:
            clusters[index] = payload
            return
    clusters.append(payload)



def delete_cluster(config: dict[str, Any], cluster_id: str) -> bool:
    clusters = config.setdefault('clusters', [])
    original = len(clusters)
    config['clusters'] = [cluster for cluster in clusters if str(cluster.get('id') or cluster.get('cluster_id') or '').strip() != cluster_id]
    return len(config['clusters']) != original



def list_clusters(config: dict[str, Any]) -> list[dict[str, Any]]:
    return list(config.get('clusters') or [])



def choose_config_path(repo_root: Path, settings: dict[str, Any]) -> Path:
    existing = settings.get('config_path') or DEFAULT_CONFIG_RELATIVE
    raw = prompt_text(
        'Where should the editable config file live? You can give a YAML file path or a folder; if you give a folder, project_config.yaml will be created inside it',
        default=str(existing),
    )
    return normalize_config_destination(raw, repo_root)



def summarize_saved_settings(settings: dict[str, Any]) -> None:
    print('Saved defaults currently are:')
    for key in ['project_root', 'output_dir', 'config_path', 'default_format']:
        value = settings.get(key)
        if value:
            print(f'  - {key}: {value}')



def setup_interactive(repo_root: Path | None = None) -> int:
    base = repo_root or _repo_root()
    settings = load_settings(base)
    print_section('Initial setup')
    if settings:
        summarize_saved_settings(settings)
        if not prompt_yes_no('Do you want to review and possibly change these saved defaults?', default=True):
            print(f'Kept existing settings file: {_settings_path(base)}')
            return 0

    project_root_input = prompt_text(
        'Where is the root folder that contains your .do files? Give a path relative to this repo when possible',
        default=str(settings.get('project_root') or 'example/project'),
    )
    output_dir_input = prompt_text(
        'Where should generated outputs go? This folder will hold PNG, SVG, DOT, and validation files',
        default=str(settings.get('output_dir') or DEFAULT_OUTPUT_DIR),
    )
    project_root_path = resolve_user_path(project_root_input, base)
    output_dir_path = resolve_user_path(output_dir_input, base)
    project_root = portable_path(project_root_path, base)
    output_dir = portable_path(output_dir_path, base)
    config_path = choose_config_path(base, settings)
    config = load_or_create_config(config_path, project_root=project_root)

    print_section('Display choices')
    theme = prompt_choice('Choose a color theme.', THEME_HELP, str(config.get('display', {}).get('theme', 'modern-light')))
    view = prompt_choice('Choose the main graph view.', VIEW_HELP, str(config.get('display', {}).get('view', 'overview')))
    label_style = prompt_choice('Choose how node labels should look.', LABEL_STYLE_HELP, str(config.get('display', {}).get('node_label_style', 'basename')))
    label_depth = prompt_int('How many parent folders should be included in labels when basename-style labels are used?', int(config.get('display', {}).get('label_path_depth', 0)))
    show_extensions = prompt_yes_no('Should file extensions stay visible in node labels?', bool(config.get('display', {}).get('show_extensions', True)))
    update_display_settings(config, theme, view, label_style, label_depth, show_extensions)
    config['project_root'] = project_root
    save_config(config_path, config)

    default_format = prompt_choice('What output format should the main render script use by default?', FORMAT_HELP, str(settings.get('default_format') or 'png'))
    settings_payload = {
        'project_root': project_root,
        'output_dir': output_dir,
        'config_path': portable_path(config_path, base),
        'default_format': default_format,
    }
    save_settings(settings_payload, base)
    print(f'Saved settings to {_settings_path(base)}')
    print(f'Saved editable config to {config_path}')
    return 0



def _import_cli_main():
    from stata_pipeline_flow.cli.main import main as cli_main
    return cli_main



def run_cli(args: list[str]) -> int:
    cli_main = _import_cli_main()
    return int(cli_main(args))



def ensure_settings_or_setup(repo_root: Path | None = None) -> dict[str, Any]:
    base = repo_root or _repo_root()
    settings = load_settings(base)
    if settings:
        return settings
    print('No saved setup was found yet. Running the initial setup first.')
    setup_interactive(base)
    return load_settings(base)



def render_interactive(repo_root: Path | None = None) -> int:
    base = repo_root or _repo_root()
    settings = ensure_settings_or_setup(base)
    summarize_saved_settings(settings)
    change = prompt_yes_no('Do you want to change any run settings just for this render?', default=False)
    project_root = str(settings['project_root'])
    output_dir = str(settings['output_dir'])
    config_path = str(settings['config_path'])
    output_format = str(settings.get('default_format') or 'png')
    keep_dot = False

    if change:
        project_root = ensure_relative(prompt_text('Project root with .do files', default=project_root))
        output_dir = ensure_relative(prompt_text('Output directory for generated files', default=output_dir))
        output_format = prompt_choice('Choose the output format for this run.', FORMAT_HELP, output_format)
        keep_dot = prompt_yes_no('Also keep the intermediate DOT file?', default=(output_format != 'dot'))
    else:
        keep_dot = output_format != 'dot'

    output_base = prompt_text('What should the output file be called, without extension?', default='pipeline_overview')
    output_path = str((resolve_user_path(output_dir, base) / f'{output_base}.{output_format}')).replace('\\', '/')
    args = ['render-image' if output_format != 'dot' else 'render-dot', '--project-root', project_root, '--config', config_path, '--output', output_path]
    if output_format != 'dot' and keep_dot:
        args.extend(['--dot-output', str((resolve_user_path(output_dir, base) / f'{output_base}.dot')).replace('\\', '/')])
        args.extend(['--format', output_format])
    print(f'Running: {" ".join(args)}')
    return run_cli(args)



def inspect_interactive(repo_root: Path | None = None) -> int:
    base = repo_root or _repo_root()
    settings = ensure_settings_or_setup(base)
    summarize_saved_settings(settings)
    action = prompt_choice(
        'What do you want to inspect?',
        {
            'summary': 'quick terminal overview; best first check',
            'validate': 'write a JSON diagnostics report',
            'both': 'print the summary and also write the validation report',
        },
        'both',
    )
    project_root = str(settings['project_root'])
    config_path = str(settings['config_path'])
    output_dir = str(settings['output_dir'])
    status = 0
    if action in {'summary', 'both'}:
        status = run_cli(['summary', '--project-root', project_root, '--config', config_path])
    if action in {'validate', 'both'}:
        validation_path = str((resolve_user_path(output_dir, base) / 'validation_report.json')).replace('\\', '/')
        status = run_cli(['validate', '--project-root', project_root, '--config', config_path, '--output', validation_path])
    return status



def edit_exclusions_interactive(repo_root: Path | None = None) -> int:
    base = repo_root or _repo_root()
    settings = ensure_settings_or_setup(base)
    config_path = resolve_user_path(str(settings['config_path']), base)
    config = load_or_create_config(config_path, project_root=str(settings['project_root']))
    print_section('Exclusion editor')
    print('You can add project-relative folder paths, specific file names, or glob patterns.')
    print('Type F when you are finished.')
    while True:
        exclusions = config.setdefault('exclusions', {})
        print('\nCurrent exclusions:')
        print(f"  - paths: {exclusions.get('paths', [])}")
        print(f"  - folder_names: {exclusions.get('folder_names', [])}")
        print(f"  - file_names: {exclusions.get('file_names', [])}")
        print(f"  - globs: {exclusions.get('globs', [])}")
        action = input('Choose action: add-path / add-folder-name / add-file-name / add-glob / remove / F: ').strip()
        if not action:
            continue
        lowered = action.lower()
        if lowered == 'f':
            break
        if lowered == 'remove':
            key = prompt_choice('Which list do you want to remove from?', {
                'paths': 'remove a specific project-relative path',
                'folder_names': 'remove a folder name that is ignored everywhere',
                'file_names': 'remove a file name that is ignored everywhere',
                'globs': 'remove a wildcard pattern such as *.log',
            }, 'paths')
            value = prompt_text('Enter the exact existing value to remove')
            update_exclusions_list(config, key, value, remove=True)
            continue
        mapping = {
            'add-path': ('paths', 'Enter a project-relative path to ignore. Example: old_versions or data/temp_exports'),
            'add-folder-name': ('folder_names', 'Enter a folder name to ignore everywhere. Example: archive or old'),
            'add-file-name': ('file_names', 'Enter a file name to ignore everywhere. Example: notes.txt'),
            'add-glob': ('globs', 'Enter a wildcard pattern. Example: *.log or *_draft.dta'),
        }
        if lowered not in mapping:
            print('That action is not supported.')
            continue
        key, question = mapping[lowered]
        value = prompt_text(question)
        update_exclusions_list(config, key, value)
    save_config(config_path, config)
    print(f'Saved updated exclusions to {config_path}')
    return 0



def manage_clusters_interactive(repo_root: Path | None = None) -> int:
    base = repo_root or _repo_root()
    settings = ensure_settings_or_setup(base)
    config_path = resolve_user_path(str(settings['config_path']), base)
    config = load_or_create_config(config_path, project_root=str(settings['project_root']))
    print_section('Cluster editor')
    print('Clusters are manual groupings on top of the automatic clustering.')
    print('For cluster members, add script paths and folder paths relative to the project root.')
    print('Type F when you are finished.')
    while True:
        current = list_clusters(config)
        print('\nCurrent clusters:')
        if not current:
            print('  - none yet')
        for cluster in current:
            cid = str(cluster.get('id') or cluster.get('cluster_id') or '')
            print(f'  - {cid}: members={cluster.get("members", [])}')
        action = input('Choose action: add / edit / delete / F: ').strip().lower()
        if not action:
            continue
        if action == 'f':
            break
        if action == 'delete':
            cluster_id = prompt_text('Enter the cluster id to delete')
            removed = delete_cluster(config, cluster_id)
            print('Deleted.' if removed else 'No cluster with that id was found.')
            continue
        if action not in {'add', 'edit'}:
            print('That action is not supported.')
            continue
        existing_id = ''
        if action == 'edit':
            existing_id = prompt_text('Enter the existing cluster id to edit')
        cluster_id = prompt_text('Cluster id (short machine-friendly name)', default=existing_id or None)
        label = prompt_text('Cluster label (human-friendly name)', default=cluster_id)
        lane = prompt_text('Optional lane name; press Enter to leave empty', default='', allow_empty=True)
        order_raw = prompt_text('Optional order number; press Enter to leave empty', default='', allow_empty=True)
        order = int(order_raw) if order_raw else None
        collapse = prompt_yes_no('Collapse this cluster into a summary box?', default=False)
        print('Now add members. Enter one script path or folder path at a time. Type F when finished.')
        members: list[str] = []
        while True:
            member = input('Member path or F: ').strip()
            if not member:
                continue
            if member.lower() == 'f':
                break
            cleaned = ensure_relative(member)
            if cleaned not in members:
                members.append(cleaned)
        upsert_cluster(config, cluster_id, label=label, members=members, lane=lane or None, order=order, collapse=collapse)
    save_config(config_path, config)
    print(f'Saved updated clusters to {config_path}')
    return 0
