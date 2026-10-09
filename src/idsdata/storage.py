"""Where dataset files live on disk and how they are checked."""

from __future__ import annotations

import hashlib
import os

from pathlib import Path
from typing import TYPE_CHECKING

from idsdata.registry import get as get_release

if TYPE_CHECKING:
    from idsdata.registry import Release

ENV_VAR = 'IDSDATA_DIR'
_CHUNK_SIZE = 1024 * 1024


class DataNotFoundError(FileNotFoundError):
    """Raised when none of a release's files are in the data directory."""


class ChecksumsUnavailableError(LookupError):
    """Raised when the registry holds no checksums for a release yet."""


class ChecksumMismatchError(ValueError):
    """Raised when a file on disk does not match its recorded SHA-256."""

    def __init__(self, path: Path, expected: str, actual: str) -> None:
        super().__init__(f'checksum mismatch for {path}\n  expected sha256: {expected}\n  actual sha256:   {actual}')
        self.path: Path = path
        self.expected: str = expected
        self.actual: str = actual


def data_root(data_dir: str | os.PathLike[str] | None = None) -> Path:
    """Return the data directory: the argument, else ``IDSDATA_DIR``, else ``~/.cache/idsdata``."""
    if data_dir is not None:
        return Path(data_dir).expanduser()
    from_env = os.environ.get(ENV_VAR)
    if from_env:
        return Path(from_env).expanduser()
    return Path.home() / '.cache' / 'idsdata'


def release_dir(name: str, version: str, data_dir: str | os.PathLike[str] | None = None) -> Path:
    """Return the directory that holds one release's files."""
    release = get_release(name, version)
    return data_root(data_dir) / release.name / release.version


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def pointer(release: Release, directory: Path) -> str:
    """Explain where to get a release and where to put it."""
    if release.access == 'form':
        how = 'Fill in the request form on that page and download the files yourself.'
    else:
        how = 'Download the files from that page.'
    lines = [
        f'{release.name} {release.version} is not distributed with idsdata.',
        f'  Download page: {release.download_page}',
        f'  {how}',
        f'  Terms: {release.terms}',
        f'  Put the files, with their original names, in: {directory}',
    ]
    if release.files:
        lines.append('  Expected files: ' + ', '.join(entry.name for entry in release.files))
    lines.append(f'  Then run: idsdata verify {release.name} {release.version}')
    lines.append(f'  Please cite the data: idsdata cite {release.name} {release.version}')
    return '\n'.join(lines)


def verify(name: str, version: str, data_dir: str | os.PathLike[str] | None = None) -> tuple[Path, ...]:
    """Check every file of a release that is present and return the verified paths."""
    release = get_release(name, version)
    directory = data_root(data_dir) / release.name / release.version
    if not release.files:
        raise ChecksumsUnavailableError(
            f'no checksums are recorded for {release.name} {release.version} yet, so its files cannot be verified'
        )
    present = [(entry, directory / entry.name) for entry in release.files if (directory / entry.name).is_file()]
    if not present:
        raise DataNotFoundError(pointer(release, directory))
    for entry, path in present:
        actual = sha256_file(path)
        if actual != entry.sha256:
            raise ChecksumMismatchError(path, entry.sha256, actual)
    return tuple(path for _, path in present)
