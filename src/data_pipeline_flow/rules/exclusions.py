from __future__ import annotations

from pathlib import PurePosixPath

from data_pipeline_flow.config.schema import ExclusionConfig


PRESET_LIBRARY: dict[str, ExclusionConfig] = {
    'generated_outputs': ExclusionConfig(
        prefixes=['viewer_output/'],
        folder_names=['viewer_output'],
    ),
    'archival_folders': ExclusionConfig(
        folder_names=['archive', '~old', 'old', 'backup'],
        globs=['*.bak'],
    ),
    'python_runtime': ExclusionConfig(
        prefixes=['.git/'],
        folder_names=['__pycache__', '.pytest_cache'],
    ),
}


def _normalize_prefix(value: str) -> str:
    return str(PurePosixPath(value.rstrip('/')))


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        if value not in seen:
            ordered.append(value)
            seen.add(value)
    return ordered


def resolve_exclusion_config(config: ExclusionConfig) -> ExclusionConfig:
    prefixes = list(config.prefixes)
    globs = list(config.globs)
    exact_names = list(config.exact_names)
    exact_paths = list(config.exact_paths)
    folder_names = list(config.folder_names)

    for preset_name in config.presets:
        preset = PRESET_LIBRARY.get(preset_name)
        if preset is None:
            available = ', '.join(sorted(PRESET_LIBRARY))
            raise ValueError(f'Unknown exclusion preset: {preset_name}. Available presets: {available}')
        prefixes.extend(preset.prefixes)
        globs.extend(preset.globs)
        exact_names.extend(preset.exact_names)
        exact_paths.extend(preset.exact_paths)
        folder_names.extend(preset.folder_names)

    exact_names.extend(config.file_names)
    for path in config.paths:
        if path.endswith('/'):
            prefixes.append(path)
        else:
            exact_paths.append(path)

    return ExclusionConfig(
        prefixes=_dedupe(prefixes),
        globs=_dedupe(globs),
        exact_names=_dedupe(exact_names),
        exact_paths=_dedupe([str(PurePosixPath(path.rstrip('/'))) for path in exact_paths]),
        folder_names=_dedupe(folder_names),
        paths=[],
        file_names=[],
        presets=list(config.presets),
    )


def is_excluded(path: str, config: ExclusionConfig) -> bool:
    norm = str(PurePosixPath(path.rstrip('/')))
    prefixes = [_normalize_prefix(prefix) for prefix in config.prefixes]
    exact_paths = {str(PurePosixPath(value.rstrip('/'))) for value in config.exact_paths}
    if any(norm == prefix or norm.startswith(f'{prefix}/') for prefix in prefixes):
        return True
    if norm in exact_paths:
        return True
    if PurePosixPath(norm).name in set(config.exact_names):
        return True
    all_parts = PurePosixPath(norm).parts
    # folder_names should only match directory components, not the filename itself.
    # If the original path ends with '/' it is a directory path, so all parts are
    # directory components. Otherwise, only the leading parts (excluding the last,
    # which is the filename) are directory components.
    is_dir_path = path.endswith('/')
    dir_parts = set(all_parts) if is_dir_path else set(all_parts[:-1])
    if any(folder in dir_parts for folder in config.folder_names):
        return True
    if any(PurePosixPath(norm).match(glob) for glob in config.globs):
        return True
    return False
