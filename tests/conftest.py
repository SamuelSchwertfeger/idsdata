from __future__ import annotations

import hashlib

from typing import TYPE_CHECKING

import pytest

from idsdata import registry
from idsdata.registry import FileEntry, Release

if TYPE_CHECKING:
    from pathlib import Path

# Synthetic release: made-up file names and contents, hashed here in code.
SYNTHETIC_FILES = {
    'archive.bin': b'synthetic archive bytes',
    'monday.txt': b'a,b,label\n1,2,x\n',
    'tuesday.txt': b'a,b,label\n3,4,y\n',
}


def _synthetic_release(version: str, access: str, files: tuple[FileEntry, ...]) -> Release:
    return Release(
        name='synthetic',
        version=version,
        title='Synthetic',
        summary='Made up for the tests.',
        homepage='https://example.org/',
        download_page='https://example.org/download',
        access='form' if access == 'form' else 'direct',
        terms='Made-up terms.',
        citations=(registry.SHARAFALDIN_2018,),
        files=files,
    )


@pytest.fixture
def synthetic_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the registry with synthetic releases: ``v1`` (direct), ``gated`` (form), ``empty`` (no files)."""
    files = tuple(
        FileEntry(name=name, sha256=hashlib.sha256(content).hexdigest(), size=len(content))
        for name, content in SYNTHETIC_FILES.items()
    )
    releases = [
        _synthetic_release('v1', 'direct', files),
        _synthetic_release('gated', 'form', files),
        _synthetic_release('empty', 'direct', ()),
    ]
    monkeypatch.setattr(registry, 'REGISTRY', {(release.name, release.version): release for release in releases})


@pytest.fixture
def data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty data directory, with ``IDSDATA_DIR`` unset."""
    monkeypatch.delenv('IDSDATA_DIR', raising=False)
    return tmp_path / 'data'


def place(data_dir: Path, version: str, name: str, content: bytes | None = None) -> Path:
    """Write one synthetic file into the release directory."""
    path = data_dir / 'synthetic' / version / name
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_bytes(SYNTHETIC_FILES[name] if content is None else content)
    return path
