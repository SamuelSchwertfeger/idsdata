"""Versioned, checksummed loaders and a linter for intrusion-detection datasets."""

from importlib.metadata import version as _package_version

from idsdata import registry
from idsdata.registry import Citation, FileEntry, Release, UnknownDatasetError
from idsdata.storage import ChecksumMismatchError, ChecksumsUnavailableError, DataNotFoundError, verify

__version__ = _package_version('idsdata')

__all__ = [
    'ChecksumMismatchError',
    'ChecksumsUnavailableError',
    'Citation',
    'DataNotFoundError',
    'FileEntry',
    'Release',
    'UnknownDatasetError',
    '__version__',
    'cite',
    'datasets',
    'info',
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
