"""Fetch a release's archive from its official host, when that host allows it."""

from __future__ import annotations

import shutil
import urllib.request

from importlib.metadata import version as package_version
from typing import IO, TYPE_CHECKING, cast

from idsdata.registry import get as get_release
from idsdata.storage import ChecksumMismatchError, data_root, pointer, sha256_file

if TYPE_CHECKING:
    import os

    from pathlib import Path

    from idsdata.model import FileEntry, Release

_TIMEOUT_SECONDS = 60


class DownloadNotAllowedError(RuntimeError):
    """Raised when a release has to be downloaded by hand."""


def downloadable(release: Release) -> tuple[FileEntry, ...]:
    """Return the files idsdata may fetch itself: none for releases behind a form."""
    if release.access != 'direct':
        return ()
    return tuple(entry for entry in release.files if entry.url is not None and entry.url.startswith('https://'))


def notice(release: Release, directory: Path) -> str:
    """The terms and citation notice shown before anything is fetched."""
    entries = downloadable(release)
    megabytes = sum(entry.size for entry in entries) / 1_000_000
    lines = [
        f'{release.name} {release.version}: {release.title}',
        f'  Terms: {release.terms}',
        f'  Please cite the data: idsdata cite {release.name} {release.version}',
        f'  Size: {megabytes:.0f} MB',
        f'  To: {directory}',
    ]
    lines.extend(f'  From: {entry.url}' for entry in entries)
    return '\n'.join(lines)


def download(name: str, version: str, data_dir: str | os.PathLike[str] | None = None) -> tuple[Path, ...]:
    """Download and verify a release's archive. Files already present and correct are kept."""
    release = get_release(name, version)
    directory = data_root(data_dir) / release.name / release.version
    entries = downloadable(release)
    if not entries:
        raise DownloadNotAllowedError(pointer(release, directory))
    directory.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    for entry in entries:
        target = directory / entry.name
        paths.append(target)
        if target.is_file() and sha256_file(target) == entry.sha256:
            continue
        partial = target.with_name(target.name + '.part')
        request = urllib.request.Request(
            str(entry.url), headers={'User-Agent': f'idsdata/{package_version("idsdata")}'}
        )
        with (
            cast('IO[bytes]', urllib.request.urlopen(request, timeout=_TIMEOUT_SECONDS)) as response,
            partial.open('wb') as sink,
        ):
            shutil.copyfileobj(response, sink)
        actual = sha256_file(partial)
        if actual != entry.sha256:
            partial.unlink()
            raise ChecksumMismatchError(target, entry.sha256, actual)
        _ = partial.replace(target)
    return tuple(paths)
