"""Read a verified release into a pandas DataFrame."""

from __future__ import annotations

import shutil
import zipfile

from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.csv as pacsv
import pyarrow.parquet as pq

from idsdata.registry import get as get_release
from idsdata.storage import ChecksumsUnavailableError, DataNotFoundError, check, data_root, pointer

if TYPE_CHECKING:
    import os

    from collections.abc import Iterable
    from pathlib import Path

    import pandas as pd

    from idsdata.model import FileEntry, Release

# Bump when the columns written to the parquet cache change.
CACHE_VERSION = 1

_ARROW_TYPES: dict[str, pa.DataType] = {'int64': pa.int64(), 'double': pa.float64(), 'string': pa.string()}


def _select(release: Release, files: Iterable[str] | None) -> list[FileEntry]:
    tables = [entry for entry in release.files if entry.kind == 'table']
    if files is None:
        return tables
    wanted = list(files)
    known = {entry.name for entry in tables}
    unknown = [name for name in wanted if name not in known]
    if unknown:
        known_files = ', '.join(entry.name for entry in tables)
        raise ValueError(
            f'not a file of {release.name} {release.version}: {", ".join(unknown)}; known files: {known_files}'
        )
    return [entry for entry in tables if entry.name in wanted]


def _extract_missing(release: Release, directory: Path, selected: list[FileEntry]) -> None:
    """Unpack selected tables that are absent from a verified archive in the same directory."""
    archives = {entry.name: entry for entry in release.files if entry.kind == 'archive'}
    checked: set[str] = set()
    for entry in selected:
        target = directory / entry.name
        if target.is_file() or entry.archive is None:
            continue
        archive_path = directory / entry.archive
        if not archive_path.is_file():
            continue
        if entry.archive not in checked:
            check(archives[entry.archive], archive_path)
            checked.add(entry.archive)
        partial = target.with_name(target.name + '.part')
        with zipfile.ZipFile(archive_path) as archive, archive.open(entry.name) as source, partial.open('wb') as sink:
            shutil.copyfileobj(source, sink)
        _ = partial.replace(target)


def _read_table(release: Release, entry: FileEntry, path: Path) -> pa.Table:
    types = {column.original: _ARROW_TYPES[column.dtype] for column in release.columns}
    table = pacsv.read_csv(path, convert_options=pacsv.ConvertOptions(column_types=types))
    expected = [column.original for column in release.columns]
    if table.column_names != expected:
        raise ValueError(f'{path} does not have the columns recorded for {release.name} {release.version}')
    table = table.rename_columns([column.name for column in release.columns])

    encoded = table.column('label_raw').combine_chunks().dictionary_encode()
    known = {label.raw: label for label in release.labels}
    seen: list[str] = encoded.dictionary.to_pylist()
    unknown = [raw for raw in seen if raw not in known]
    if unknown:
        raise ValueError(f'{path} has label values that are not in the registry: {unknown}')
    for name, values in [
        ('label', pa.array([known[raw].label for raw in seen], pa.string())),
        ('is_attack', pa.array([known[raw].is_attack for raw in seen], pa.bool_())),
        ('is_attempted', pa.array([known[raw].is_attempted for raw in seen], pa.bool_())),
    ]:
        table = table.append_column(name, values.take(encoded.indices))
    return table.append_column('source_file', pa.repeat(pa.scalar(entry.name, pa.string()), table.num_rows))


def _cached_table(release: Release, entry: FileEntry, directory: Path) -> pa.Table:
    stem = entry.name.rsplit('.', 1)[0]
    cache = directory / 'cache' / f'{stem}.{entry.sha256[:12]}.v{CACHE_VERSION}.parquet'
    if cache.is_file():
        return pq.read_table(cache)
    table = _read_table(release, entry, directory / entry.name)
    cache.parent.mkdir(parents=True, exist_ok=True)
    partial = cache.with_name(cache.name + '.part')
    pq.write_table(table, partial)
    _ = partial.replace(cache)
    return table


def load(
    name: str,
    version: str,
    data_dir: str | os.PathLike[str] | None = None,
    files: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Verify a release and return it as one DataFrame.

    Columns get their clean names, the source label is kept as ``label_raw`` and
    ``label``, ``is_attack``, ``is_attempted`` and ``source_file`` are added.
    No row is dropped or relabelled.
    """
    release = get_release(name, version)
    directory = data_root(data_dir) / release.name / release.version
    if not release.files or not release.columns:
        raise ChecksumsUnavailableError(
            f'no files are recorded for {release.name} {release.version} yet, so it cannot be loaded'
        )
    selected = _select(release, files)
    if directory.is_dir():
        _extract_missing(release, directory, selected)
    missing = [entry.name for entry in selected if not (directory / entry.name).is_file()]
    if missing:
        raise DataNotFoundError(f'missing: {", ".join(missing)}\n{pointer(release, directory)}')
    for entry in selected:
        check(entry, directory / entry.name)
    tables = [_cached_table(release, entry, directory) for entry in selected]
    return pa.concat_tables(tables).to_pandas()
