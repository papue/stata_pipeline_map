from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from stata_pipeline_flow.config.schema import ExclusionConfig, NormalizationConfig
from stata_pipeline_flow.model.normalize import normalize_token, to_project_relative
from stata_pipeline_flow.rules.exclusions import is_excluded


@dataclass(slots=True)
class ProjectScan:
    do_files: list[str]
    input_files: list[str]
    output_artifacts: list[str]
    excluded_files: list[str]


INPUT_SUFFIXES = {'.csv', '.dta', '.xlsx'}
OUTPUT_SUFFIXES = {'.png', '.svg', '.pdf', '.csv', '.ster', '.xlsx', '.dot', '.viz'}


def discover_project_files(project_root: Path, exclusions: ExclusionConfig, normalization: NormalizationConfig) -> ProjectScan:
    do_files: list[str] = []
    input_files: list[str] = []
    output_artifacts: list[str] = []
    excluded_files: list[str] = []

    for root, dirs, files in os.walk(project_root, topdown=True):
        root_path = Path(root)
        kept_dirs: list[str] = []
        for dirname in sorted(dirs):
            dir_path = root_path / dirname
            rel_dir, _ = to_project_relative(project_root, dir_path, normalization)
            rel_dir = normalize_token(rel_dir)
            dir_key = rel_dir if rel_dir.endswith('/') else f'{rel_dir}/'
            if is_excluded(dir_key, exclusions):
                excluded_files.append(dir_key)
            else:
                kept_dirs.append(dirname)
        dirs[:] = kept_dirs

        for filename in sorted(files):
            path = root_path / filename
            rel, _ = to_project_relative(project_root, path, normalization)
            rel = normalize_token(rel)
            if is_excluded(rel, exclusions):
                excluded_files.append(rel)
                continue
            suffix = path.suffix.lower()
            if suffix == '.do':
                do_files.append(rel)
            elif suffix in INPUT_SUFFIXES:
                input_files.append(rel)
            elif suffix in OUTPUT_SUFFIXES:
                output_artifacts.append(rel)

    return ProjectScan(
        do_files=do_files,
        input_files=input_files,
        output_artifacts=output_artifacts,
        excluded_files=sorted(set(excluded_files)),
    )
