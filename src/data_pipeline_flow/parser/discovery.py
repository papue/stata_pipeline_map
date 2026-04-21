from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os

from data_pipeline_flow.config.schema import ExclusionConfig, LanguagesConfig, NormalizationConfig
from data_pipeline_flow.model.normalize import normalize_token, to_project_relative
from data_pipeline_flow.rules.exclusions import is_excluded


@dataclass(slots=True)
class ProjectScan:
    do_files: list[str]
    py_files: list[str]
    r_files: list[str]
    input_files: list[str]
    output_artifacts: list[str]
    excluded_files: list[str]

    @property
    def script_files(self) -> list[str]:
        return self.do_files + self.py_files + self.r_files


INPUT_SUFFIXES = {
    '.csv', '.dta', '.xlsx',
    '.parquet', '.feather',
    '.rds', '.rdata', '.rda',
    '.json', '.pkl', '.pickle',
}
OUTPUT_SUFFIXES = {
    '.png', '.svg', '.pdf', '.csv', '.ster', '.xlsx', '.dot', '.viz',
    '.rds', '.rdata', '.rda',
}


def discover_project_files(
    project_root: Path,
    exclusions: ExclusionConfig,
    normalization: NormalizationConfig,
    languages: LanguagesConfig | None = None,
) -> ProjectScan:
    if languages is None:
        languages = LanguagesConfig()

    # Build the set of active script extensions (all lowercase for comparison)
    script_extensions: dict[str, str] = {}  # ext -> language key
    if languages.stata:
        for ext in languages.stata_extensions:
            script_extensions[ext.lower()] = 'stata'
    if languages.python:
        for ext in languages.python_extensions:
            script_extensions[ext.lower()] = 'python'
    if languages.r:
        for ext in languages.r_extensions:
            script_extensions[ext.lower()] = 'r'

    do_files: list[str] = []
    py_files: list[str] = []
    r_files: list[str] = []
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
            lang = script_extensions.get(suffix)
            if lang == 'stata':
                do_files.append(rel)
            elif lang == 'python':
                py_files.append(rel)
            elif lang == 'r':
                r_files.append(rel)
            elif suffix in INPUT_SUFFIXES:
                input_files.append(rel)
            elif suffix in OUTPUT_SUFFIXES:
                output_artifacts.append(rel)

    return ProjectScan(
        do_files=do_files,
        py_files=py_files,
        r_files=r_files,
        input_files=input_files,
        output_artifacts=output_artifacts,
        excluded_files=sorted(set(excluded_files)),
    )
