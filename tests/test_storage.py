from __future__ import annotations

import hashlib

from pathlib import Path

import pytest

import idsdata

from idsdata import cli, storage
from tests.conftest import SYNTHETIC_FILES, place


def test_data_root_prefers_the_argument(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('IDSDATA_DIR', str(tmp_path / 'from-env'))
    assert storage.data_root(tmp_path / 'from-arg') == tmp_path / 'from-arg'


def test_data_root_falls_back_to_the_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv('IDSDATA_DIR', str(tmp_path / 'from-env'))
    assert storage.data_root() == tmp_path / 'from-env'


@pytest.mark.parametrize('value', [None, ''])
def test_data_root_defaults_to_the_user_cache(value: str | None, monkeypatch: pytest.MonkeyPatch) -> None:
    if value is None:
        monkeypatch.delenv('IDSDATA_DIR', raising=False)
    else:
        monkeypatch.setenv('IDSDATA_DIR', value)
    assert storage.data_root() == Path.home() / '.cache' / 'idsdata'


def test_release_dir_layout(data_dir: Path) -> None:
    assert storage.release_dir('cic-ids2017', 'engelen2021', data_dir) == data_dir / 'cic-ids2017' / 'engelen2021'


def test_release_dir_rejects_unknown_releases(data_dir: Path) -> None:
    with pytest.raises(idsdata.UnknownDatasetError):
        _ = storage.release_dir('cic-ids2017', 'nope', data_dir)


def test_sha256_file_reads_in_chunks(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, '_CHUNK_SIZE', 4)
    path = tmp_path / 'blob'
    _ = path.write_bytes(b'0123456789')
    assert storage.sha256_file(path) == hashlib.sha256(b'0123456789').hexdigest()


@pytest.mark.usefixtures('synthetic_registry')
def test_verify_returns_every_file_when_all_are_present(data_dir: Path) -> None:
    placed = [place(data_dir, 'v1', name) for name in SYNTHETIC_FILES]
    assert idsdata.verify('synthetic', 'v1', data_dir) == tuple(placed)


@pytest.mark.usefixtures('synthetic_registry')
def test_verify_checks_only_what_is_present(data_dir: Path) -> None:
    placed = place(data_dir, 'v1', 'monday.csv')
    assert idsdata.verify('synthetic', 'v1', data_dir) == (placed,)


@pytest.mark.usefixtures('synthetic_registry')
def test_verify_uses_the_environment_variable(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    placed = place(data_dir, 'v1', 'archive.zip')
    monkeypatch.setenv('IDSDATA_DIR', str(data_dir))
    assert idsdata.verify('synthetic', 'v1') == (placed,)


@pytest.mark.usefixtures('synthetic_registry')
def test_verify_mismatch_reports_both_hashes(data_dir: Path) -> None:
    _ = place(data_dir, 'v1', 'monday.csv')
    tampered = place(data_dir, 'v1', 'tuesday.csv', b'tampered')
    with pytest.raises(idsdata.ChecksumMismatchError) as raised:
        _ = idsdata.verify('synthetic', 'v1', data_dir)
    error = raised.value
    assert error.path == tampered
    assert error.expected == hashlib.sha256(SYNTHETIC_FILES['tuesday.csv']).hexdigest()
    assert error.actual == hashlib.sha256(b'tampered').hexdigest()
    assert error.expected in str(error)
    assert error.actual in str(error)


@pytest.mark.usefixtures('synthetic_registry')
def test_verify_without_files_points_to_the_source(data_dir: Path) -> None:
    with pytest.raises(idsdata.DataNotFoundError) as raised:
        _ = idsdata.verify('synthetic', 'v1', data_dir)
    message = str(raised.value)
    assert 'https://example.org/download' in message
    assert str(data_dir / 'synthetic' / 'v1') in message
    assert 'archive.zip, monday.csv, tuesday.csv' in message
    assert 'idsdata cite synthetic v1' in message
    assert 'Made-up terms.' in message


@pytest.mark.usefixtures('synthetic_registry')
def test_pointer_wording_depends_on_access(data_dir: Path) -> None:
    gated = storage.pointer(idsdata.info('synthetic', 'gated'), data_dir)
    direct = storage.pointer(idsdata.info('synthetic', 'v1'), data_dir)
    assert 'request form' in gated
    assert 'request form' not in direct


@pytest.mark.usefixtures('synthetic_registry')
def test_verify_without_recorded_checksums(data_dir: Path) -> None:
    with pytest.raises(idsdata.ChecksumsUnavailableError, match='no checksums are recorded for synthetic empty'):
        _ = idsdata.verify('synthetic', 'empty', data_dir)


def test_real_registry_has_no_checksums_yet_or_valid_ones(data_dir: Path) -> None:
    for name, versions in idsdata.datasets().items():
        for version in versions:
            if not idsdata.info(name, version).files:
                with pytest.raises(idsdata.ChecksumsUnavailableError):
                    _ = idsdata.verify(name, version, data_dir)


@pytest.mark.usefixtures('synthetic_registry')
def test_cli_where_prints_only_the_path_on_stdout(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(['where', 'synthetic', 'v1', '--data-dir', str(data_dir)]) == 0
    captured = capsys.readouterr()
    assert captured.out.strip() == str(data_dir / 'synthetic' / 'v1')
    assert 'https://example.org/download' in captured.err


@pytest.mark.usefixtures('synthetic_registry')
def test_cli_where_is_quiet_once_the_directory_exists(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _ = place(data_dir, 'v1', 'monday.csv')
    assert cli.main(['where', 'synthetic', 'v1', '--data-dir', str(data_dir)]) == 0
    assert capsys.readouterr().err == ''


@pytest.mark.usefixtures('synthetic_registry')
def test_cli_verify_ok(data_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    placed = place(data_dir, 'v1', 'monday.csv')
    assert cli.main(['verify', 'synthetic', 'v1', '--data-dir', str(data_dir)]) == 0
    assert capsys.readouterr().out.strip() == f'ok  {placed}'


@pytest.mark.usefixtures('synthetic_registry')
@pytest.mark.parametrize(
    ['version', 'tamper', 'expected'],
    [
        ('v1', False, 'is not distributed with idsdata'),
        ('v1', True, 'checksum mismatch'),
        ('empty', False, 'no checksums are recorded'),
    ],
)
def test_cli_verify_failures_exit_1(
    version: str, tamper: bool, expected: str, data_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    if tamper:
        _ = place(data_dir, 'v1', 'monday.csv', b'tampered')
    assert cli.main(['verify', 'synthetic', version, '--data-dir', str(data_dir)]) == 1
    captured = capsys.readouterr()
    assert captured.out == ''
    assert expected in captured.err
