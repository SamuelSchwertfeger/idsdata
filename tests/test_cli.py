import pytest

import idsdata

from idsdata import cli


def test_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(['list']) == 0
    assert capsys.readouterr().out.splitlines() == [
        'cic-ids2017 original-flows',
        'cic-ids2017 original-ml',
        'cic-ids2017 engelen2021',
    ]


def test_info(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(['info', 'cic-ids2017', 'original-flows']) == 0
    out = capsys.readouterr().out
    assert 'https://www.unb.ca/cic/datasets/ids-2017.html' in out
    assert 'request form' in out
    assert 'GeneratedLabelledFlows.zip' in out


def test_cite_matches_the_python_api(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(['cite', 'cic-ids2017', 'engelen2021']) == 0
    assert capsys.readouterr().out.rstrip('\n') == idsdata.cite('cic-ids2017', 'engelen2021')


def test_unknown_release_exits_2_with_a_message(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(['info', 'cic-ids2017', 'nope']) == 2
    captured = capsys.readouterr()
    assert captured.out == ''
    assert 'unknown version' in captured.err


def test_no_command_is_a_usage_error() -> None:
    with pytest.raises(SystemExit) as raised:
        _ = cli.main([])
    assert raised.value.code == 2


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        _ = cli.main(['--version'])
    assert raised.value.code == 0
    assert idsdata.__version__ in capsys.readouterr().out
