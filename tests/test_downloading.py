from __future__ import annotations

import io
import urllib.request

from typing import TYPE_CHECKING

import pytest

import idsdata

from idsdata import cli, downloading
from tests.conftest import SYNTHETIC_FILES, place

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


class FakeHost:
    """Stands in for ``urllib.request.urlopen`` and records what was asked for."""

    def __init__(self, content: bytes) -> None:
        self.content: bytes = content
        self.requests: list[urllib.request.Request] = []

    def __call__(self, request: urllib.request.Request, timeout: float) -> io.BytesIO:
        assert timeout > 0
        self.requests.append(request)
        return io.BytesIO(self.content)


def answering(reply: str) -> Callable[[str], str]:
    def ask(_prompt: str) -> str:
        return reply

    return ask


@pytest.fixture
def host(monkeypatch: pytest.MonkeyPatch) -> FakeHost:
    fake = FakeHost(SYNTHETIC_FILES['archive.zip'])
    monkeypatch.setattr(urllib.request, 'urlopen', fake)
    return fake


@pytest.mark.usefixtures('synthetic_registry')
def test_download_fetches_and_verifies_the_archive(data_dir: Path, host: FakeHost) -> None:
    paths = idsdata.download('synthetic', 'v1', data_dir)
    target = data_dir / 'synthetic' / 'v1' / 'archive.zip'
    assert paths == (target,)
    assert target.read_bytes() == SYNTHETIC_FILES['archive.zip']
    assert [request.full_url for request in host.requests] == ['https://example.org/archive.zip']
    assert host.requests[0].get_header('User-agent', '').startswith('idsdata/')
    assert len(idsdata.load('synthetic', 'v1', data_dir)) == 5


@pytest.mark.usefixtures('synthetic_registry')
def test_download_keeps_a_file_that_is_already_correct(data_dir: Path, host: FakeHost) -> None:
    target = place(data_dir, 'v1', 'archive.zip')
    assert idsdata.download('synthetic', 'v1', data_dir) == (target,)
    assert host.requests == []


@pytest.mark.usefixtures('synthetic_registry')
def test_download_replaces_a_file_that_is_wrong(data_dir: Path, host: FakeHost) -> None:
    target = place(data_dir, 'v1', 'archive.zip', b'truncated')
    _ = idsdata.download('synthetic', 'v1', data_dir)
    assert target.read_bytes() == SYNTHETIC_FILES['archive.zip']
    assert len(host.requests) == 1


@pytest.mark.usefixtures('synthetic_registry')
def test_download_discards_a_file_with_the_wrong_hash(data_dir: Path, host: FakeHost) -> None:
    host.content = b'not the archive'
    with pytest.raises(idsdata.ChecksumMismatchError):
        _ = idsdata.download('synthetic', 'v1', data_dir)
    assert list((data_dir / 'synthetic' / 'v1').iterdir()) == []


@pytest.mark.usefixtures('synthetic_registry')
@pytest.mark.parametrize('version', ['gated', 'empty'])
def test_download_refuses_releases_it_may_not_fetch(data_dir: Path, host: FakeHost, version: str) -> None:
    with pytest.raises(idsdata.DownloadNotAllowedError, match='https://example.org/download'):
        _ = idsdata.download('synthetic', version, data_dir)
    assert host.requests == []
    assert not data_dir.exists()


@pytest.mark.parametrize('version', ['original-flows', 'original-ml'])
def test_the_original_versions_are_never_fetched(version: str) -> None:
    assert downloading.downloadable(idsdata.info('cic-ids2017', version)) == ()


def test_recorded_download_urls_are_https() -> None:
    for name, versions in idsdata.datasets().items():
        for version in versions:
            release = idsdata.info(name, version)
            urls = [entry.url for entry in release.files if entry.url is not None]
            assert all(url.startswith('https://') for url in urls)
            assert len(downloading.downloadable(release)) == len(urls)


@pytest.mark.usefixtures('synthetic_registry')
def test_cli_download_shows_the_terms_and_asks_first(
    data_dir: Path, host: FakeHost, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr('builtins.input', answering('n'))
    assert cli.main(['download', 'synthetic', 'v1', '--data-dir', str(data_dir)]) == 1
    captured = capsys.readouterr()
    assert 'Terms: Made-up terms.' in captured.out
    assert 'idsdata cite synthetic v1' in captured.out
    assert 'https://example.org/archive.zip' in captured.out
    assert 'nothing downloaded' in captured.err
    assert host.requests == []


@pytest.mark.usefixtures('synthetic_registry')
def test_cli_download_after_a_yes(
    data_dir: Path, host: FakeHost, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr('builtins.input', answering('Y'))
    assert cli.main(['download', 'synthetic', 'v1', '--data-dir', str(data_dir)]) == 0
    assert f'ok  {data_dir / "synthetic" / "v1" / "archive.zip"}' in capsys.readouterr().out
    assert len(host.requests) == 1


@pytest.mark.usefixtures('synthetic_registry')
def test_cli_download_without_a_terminal_downloads_nothing(
    data_dir: Path, host: FakeHost, monkeypatch: pytest.MonkeyPatch
) -> None:
    def no_terminal(_prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr('builtins.input', no_terminal)
    assert cli.main(['download', 'synthetic', 'v1', '--data-dir', str(data_dir)]) == 1
    assert host.requests == []


@pytest.mark.usefixtures('synthetic_registry')
def test_cli_download_with_yes_does_not_ask(data_dir: Path, host: FakeHost, monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(_prompt: str) -> str:
        raise AssertionError('asked despite --yes')

    monkeypatch.setattr('builtins.input', fail)
    assert cli.main(['download', 'synthetic', 'v1', '--data-dir', str(data_dir), '--yes']) == 0
    assert len(host.requests) == 1


@pytest.mark.usefixtures('synthetic_registry')
def test_cli_download_of_a_gated_release_points_to_the_form(
    data_dir: Path, host: FakeHost, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.main(['download', 'synthetic', 'gated', '--data-dir', str(data_dir), '--yes']) == 1
    captured = capsys.readouterr()
    assert 'has to be downloaded by hand' in captured.err
    assert 'https://example.org/download' in captured.err
    assert host.requests == []


@pytest.mark.usefixtures('synthetic_registry')
def test_cli_download_reports_a_bad_hash(data_dir: Path, host: FakeHost, capsys: pytest.CaptureFixture[str]) -> None:
    host.content = b'not the archive'
    assert cli.main(['download', 'synthetic', 'v1', '--data-dir', str(data_dir), '--yes']) == 1
    assert 'idsdata:' in capsys.readouterr().err


@pytest.mark.usefixtures('synthetic_registry')
def test_cli_info_shows_when_the_files_were_retrieved(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(['info', 'synthetic', 'v1']) == 0
    assert '2020-01-01' in capsys.readouterr().out
