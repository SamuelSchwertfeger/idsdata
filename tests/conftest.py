from __future__ import annotations

import hashlib
import io
import zipfile

from typing import TYPE_CHECKING

import pytest

from idsdata import registry
from idsdata.model import Column, FileEntry, Label, Release

if TYPE_CHECKING:
    from pathlib import Path

# Everything below is made up for the tests and hashed here in code.
MONDAY = b'Flow ID,Rate/s,Count,Label\na,1.5,1,BENIGN\nb,NaN,2,BENIGN\nc,Infinity,3,Probe\n'
TUESDAY = b'Flow ID,Rate/s,Count,Label\nd,2.5,4,Probe - Attempted\ne,0.5,5,BENIGN\n'

SYNTHETIC_COLUMNS = (
    Column('Flow ID', 'flow_id', 'string'),
    Column('Rate/s', 'rate_s', 'double'),
    Column('Count', 'count', 'int64'),
    Column('Label', 'label_raw', 'string'),
)
SYNTHETIC_LABELS = (
    Label('BENIGN', 'benign', is_attack=False),
    Label('Probe', 'probe', is_attack=True),
    Label('Probe - Attempted', 'probe_attempted', is_attack=False, is_attempted=True),
)


def make_archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        for name, content in members.items():
            archive.writestr(zipfile.ZipInfo(name, date_time=(2020, 1, 1, 0, 0, 0)), content)
    return buffer.getvalue()


SYNTHETIC_FILES = {
    'archive.zip': make_archive({'monday.csv': MONDAY, 'tuesday.csv': TUESDAY}),
    'monday.csv': MONDAY,
    'tuesday.csv': TUESDAY,
}


def make_release(version: str, files: dict[str, bytes], *, form: bool = False) -> Release:
    """Build a synthetic release whose hashes match ``files``."""
    entries = tuple(
        FileEntry(
            name=name,
            sha256=hashlib.sha256(content).hexdigest(),
            size=len(content),
            kind='archive' if name.endswith('.zip') else 'table',
            archive=None if name.endswith('.zip') or 'archive.zip' not in files else 'archive.zip',
            url='https://example.org/archive.zip' if name.endswith('.zip') else None,
        )
        for name, content in files.items()
    )
    return Release(
        name='synthetic',
        version=version,
        title='Synthetic',
        summary='Made up for the tests.',
        homepage='https://example.org/',
        download_page='https://example.org/download',
        access='form' if form else 'direct',
        terms='Made-up terms.',
        citations=(registry.SHARAFALDIN_2018,),
        files=entries,
        columns=SYNTHETIC_COLUMNS if entries else (),
        labels=SYNTHETIC_LABELS if entries else (),
        retrieved='2020-01-01' if entries else None,
    )


def register(monkeypatch: pytest.MonkeyPatch, *releases: Release) -> None:
    monkeypatch.setattr(registry, 'REGISTRY', {(release.name, release.version): release for release in releases})


@pytest.fixture
def synthetic_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the registry with synthetic releases: ``v1`` (direct), ``gated`` (form), ``empty`` (no files)."""
    register(
        monkeypatch,
        make_release('v1', SYNTHETIC_FILES),
        make_release('gated', SYNTHETIC_FILES, form=True),
        make_release('empty', {}),
    )


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
