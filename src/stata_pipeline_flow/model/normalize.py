from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import posixpath
import re
import sys

from stata_pipeline_flow.config.schema import NormalizationConfig

_WINDOWS = sys.platform == 'win32'

WINDOWS_ABS_RE = re.compile(r'^[A-Za-z]:[\\/]')


@dataclass(frozen=True, slots=True)
class NormalizedPathResult:
    value: str
    was_absolute: bool


def normalize_token(token: str) -> str:
    value = str(token).strip().strip('"').strip("'").replace('\\', '/')
    if not value:
        return '.'
    value = re.sub(r'/+', '/', value)
    normalized = posixpath.normpath(value)
    return '.' if normalized == '' else normalized


def _is_absolute_like(value: str) -> bool:
    return value.startswith('/') or value.startswith('\\\\') or bool(WINDOWS_ABS_RE.match(value))


def _join_relative(base: str, suffix: str, strip_leading_dot: bool) -> str:
    if base in {'', '.'}:
        joined = suffix
    elif suffix in {'', '.'}:
        joined = base
    else:
        joined = f'{base}/{suffix}'
    joined = normalize_token(joined)
    if strip_leading_dot and joined.startswith('./'):
        joined = joined[2:]
    return joined


def _project_root_name(project_root: Path) -> str:
    direct_name = project_root.name
    if direct_name not in {'', '.'}:
        return direct_name
    resolved_name = project_root.resolve().name
    return resolved_name if resolved_name not in {'', '.'} else direct_name


def _marker_candidates(project_root: Path, config: NormalizationConfig) -> list[str]:
    markers = [
        normalize_token(str(project_root)),
        normalize_token(str(project_root.resolve())),
        normalize_token(_project_root_name(project_root)),
    ]
    markers.extend(normalize_token(marker) for marker in config.project_root_markers if marker)

    unique: list[str] = []
    seen: set[str] = set()
    for marker in markers:
        cleaned = marker.strip('/')
        if cleaned and cleaned not in seen:
            unique.append(cleaned)
            seen.add(cleaned)
    unique.sort(key=len, reverse=True)
    return unique


def _strip_to_project_suffix(raw: str, markers: list[str]) -> str | None:
    parts = [part for part in raw.split('/') if part not in {'', '.'}]
    for marker in markers:
        marker_parts = [part for part in marker.split('/') if part not in {'', '.'}]
        if not marker_parts:
            continue
        width = len(marker_parts)
        for idx in range(0, len(parts) - width + 1):
            if parts[idx:idx + width] == marker_parts:
                suffix_parts = parts[idx + width:]
                return normalize_token('/'.join(suffix_parts)) if suffix_parts else '.'
    return None


def _infer_existing_project_suffix(project_root: Path, raw: str) -> str | None:
    parts = [part for part in raw.split('/') if part not in {'', '.'}]
    for idx in range(len(parts)):
        suffix = normalize_token('/'.join(parts[idx:]))
        if suffix in {'', '.'}:
            continue
        candidate = project_root / suffix
        if candidate.exists():
            return suffix
    return None


def _case_fold(path: str) -> str:
    """On Windows, lower-case the path so that different casings of the same
    file collapse to a single node ID (e.g. Data/Cohort.DTA == data/cohort.dta)."""
    return path.lower() if _WINDOWS else path


def to_project_relative(project_root: Path, candidate: str | Path, config: NormalizationConfig | None = None) -> tuple[str, bool]:
    config = config or NormalizationConfig()
    raw = normalize_token(str(candidate))
    was_absolute = _is_absolute_like(str(candidate)) or Path(str(candidate)).is_absolute()

    for source, target in sorted(config.path_prefix_aliases.items(), key=lambda item: len(item[0]), reverse=True):
        source_norm = normalize_token(source).rstrip('/')
        target_norm = normalize_token(target)
        if raw == source_norm or raw.startswith(f'{source_norm}/'):
            suffix = raw[len(source_norm):].lstrip('/')
            aliased = _join_relative(target_norm, suffix, strip_leading_dot=config.strip_leading_dot)
            return _case_fold(aliased), was_absolute

    project_root_norm = normalize_token(str(project_root.resolve())).rstrip('/')
    if raw == project_root_norm or raw.startswith(f'{project_root_norm}/'):
        suffix = raw[len(project_root_norm):].lstrip('/')
        return _case_fold(_join_relative('.', suffix, strip_leading_dot=config.strip_leading_dot)), was_absolute

    project_root_name = _project_root_name(project_root)
    if project_root_name and (raw == project_root_name or raw.startswith(f'{project_root_name}/')):
        suffix = raw[len(project_root_name):].lstrip('/')
        return _case_fold(_join_relative('.', suffix, strip_leading_dot=config.strip_leading_dot)), was_absolute

    if was_absolute:
        stripped = _strip_to_project_suffix(raw, _marker_candidates(project_root, config))
        if stripped is not None:
            return _case_fold(_join_relative('.', stripped, strip_leading_dot=config.strip_leading_dot)), was_absolute

        inferred = _infer_existing_project_suffix(project_root, raw)
        if inferred is not None:
            return _case_fold(_join_relative('.', inferred, strip_leading_dot=config.strip_leading_dot)), was_absolute

    normalized = raw
    if config.strip_leading_dot and normalized.startswith('./'):
        normalized = normalized[2:]
    return _case_fold(normalized), was_absolute
