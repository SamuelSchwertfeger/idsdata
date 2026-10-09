"""Versioned, checksummed loaders and a linter for intrusion-detection datasets."""

from __future__ import annotations

from importlib.metadata import version as _package_version
from typing import TYPE_CHECKING

from idsdata import registry
from idsdata.model import Citation, Column, FileEntry, Label, Release
from idsdata.registry import UnknownDatasetError
from idsdata.storage import ChecksumMismatchError, ChecksumsUnavailableError, DataNotFoundError, verify

if TYPE_CHECKING:
    import os

    from collections.abc import Iterable

    import pandas as pd

__version__ = _package_version('idsdata')

__all__ = [
    'ChecksumMismatchError',
    'ChecksumsUnavailableError',
    'Citation',
    'Column',
    'DataNotFoundError',
    'FileEntry',
    'Label',
    'Release',
    'UnknownDatasetError',
    '__version__',
    'cite',
    'datasets',
    'info',
    'load',
    'verify',
]


def datasets() -> dict[str, tuple[str, ...]]:
    """Return every known dataset name with its versions."""
    found: dict[str, tuple[str, ...]] = {}
    for name, version in registry.REGISTRY:
        found[name] = (*found.get(name, ()), version)
    return found


def info(name: str, version: str) -> Release:
    """Return the registry metadata for one release."""
    return registry.get(name, version)


def cite(name: str, version: str) -> str:
    """Return the BibTeX entries to cite when using one release."""
    return '\n\n'.join(citation.bibtex() for citation in registry.get(name, version).citations)


def load(
    name: str,
    version: str,
    data_dir: str | os.PathLike[str] | None = None,
    files: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Verify a release and return it as one pandas DataFrame.

    Columns get their clean names, the source label is kept as ``label_raw`` and
    ``label``, ``is_attack``, ``is_attempted`` and ``source_file`` are added.
    No row is dropped or relabelled. ``files`` limits the load to some of the
    release's files.
    """
    # Imported here so that the command line stays quick when it does not read data.
    from idsdata.loading import load as _load

    return _load(name, version, data_dir, files)
