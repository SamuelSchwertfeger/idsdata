from __future__ import annotations

import re

from pathlib import Path

import pytest

from idsdata import lint as linting
from idsdata.lint import RULES, lint, main

# Everything below is made up for the tests.
CLEAN = b'Flow Duration,Rate/s,Label\n1,1.5,BENIGN\n2,2.5,Probe\n3,3.5,BENIGN\n'


def write(tmp_path: Path, content: bytes) -> Path:
    path = tmp_path / 'flows.csv'
    _ = path.write_bytes(content)
    return path


def found(path: Path, labels: list[str] | None = None) -> dict[str, list[str]]:
    by_rule: dict[str, list[str]] = {}
    for finding in lint(path, labels):
        by_rule.setdefault(finding.rule.name, []).append(finding.detail)
    return by_rule


def test_rules_are_complete() -> None:
    assert len({rule.id for rule in RULES}) == len(RULES)
    assert len({rule.name for rule in RULES}) == len(RULES)
    for rule in RULES:
        assert rule.severity in {'error', 'warn'}
        assert rule.explanation
        assert '\n' not in rule.explanation
        assert rule.sources, f'{rule.id} has no source'
        for source in rule.sources:
            assert source.authors
            assert source.title
            assert source.where
            assert source.url.startswith('https://')


def test_a_clean_file_has_no_findings(tmp_path: Path) -> None:
    assert lint(write(tmp_path, CLEAN)) == []


def test_duplicated_column_names(tmp_path: Path) -> None:
    content = b'Flow Duration,Rate/s, Rate/s,Label\n1,1.5,1.0,BENIGN\n2,2.5,2.0,Probe\n'
    assert found(write(tmp_path, content)) == {'duplicated-column-names': ["'Rate/s' appears 2 times"]}


def test_non_finite_values(tmp_path: Path) -> None:
    content = b'Flow Duration,Rate/s,Label\n1,NaN,BENIGN\n2,Infinity,Probe\n3,,BENIGN\n4,-Infinity,BENIGN\n'
    assert found(write(tmp_path, content)) == {
        'non-finite-values': ["2 missing or NaN cells in 'Rate/s'", "2 infinite cells in 'Rate/s'"]
    }


def test_missing_labels(tmp_path: Path) -> None:
    content = b'Flow Duration,Rate/s,Label\n1,1.5,BENIGN\n2,2.5,\n3,3.5,Probe\n'
    assert found(write(tmp_path, content)) == {'label-strings': ['1 rows have no label']}


def test_bytes_that_are_not_utf8_do_not_stop_the_run(tmp_path: Path) -> None:
    content = b'Flow Duration,Rate/s,Label\n1,1.5,BENIGN\n2,2.5,Web \x96 Probe\n3,3.5,BENIGN\n'
    path = write(tmp_path, content)
    assert lint(path) == []
    assert list(found(path, ['BENIGN'])) == ['label-strings']


def test_labels_are_checked_against_a_release_when_given(tmp_path: Path) -> None:
    path = write(tmp_path, CLEAN)
    assert found(path, ['BENIGN', 'Probe']) == {}
    assert found(path, ['BENIGN']) == {'label-strings': ["label strings the release does not define: 'Probe'"]}


def test_labels_are_read_with_the_given_encoding(tmp_path: Path) -> None:
    path = write(tmp_path, CLEAN.replace(b'Probe', b'Web \x96 XSS'))
    labels = ['BENIGN', 'Web \u2013 XSS']
    assert lint(path, labels, 'cp1252') == []
    assert found(path, labels) == {'label-strings': ["label strings the release does not define: 'Web \ufffd XSS'"]}


def test_a_file_without_a_label_column(tmp_path: Path) -> None:
    content = b'Flow Duration,Rate/s\n1,1.5\n2,2.5\n'
    assert found(write(tmp_path, content)) == {'label-strings': ['the file has no column named Label']}


def test_duplicate_rows(tmp_path: Path) -> None:
    content = CLEAN + b'1,1.5,BENIGN\n1,1.5,BENIGN\n'
    assert found(write(tmp_path, content)) == {'duplicate-rows': ['2 of 5 rows repeat an earlier row exactly']}


def test_identifier_columns(tmp_path: Path) -> None:
    content = (
        b'Flow ID, Source IP,Dst Port,Timestamp,Rate/s,Label\n'
        b'a,10.0.0.1,80,01/01/2020 10:00,1.5,BENIGN\n'
        b'b,10.0.0.2,443,01/01/2020 10:01,2.5,Probe\n'
    )
    assert found(write(tmp_path, content)) == {
        'identifier-columns': ["present: 'Flow ID', ' Source IP', 'Dst Port', 'Timestamp'"]
    }


def test_constant_columns(tmp_path: Path) -> None:
    content = b'Flow Duration,Flags,Label\n1,0,BENIGN\n2,0,Probe\n3,0,BENIGN\n'
    assert found(write(tmp_path, content)) == {'constant-columns': ["1 columns hold a single value: 'Flags'"]}


def test_a_single_class_file_is_not_a_constant_column(tmp_path: Path) -> None:
    content = b'Flow Duration,Rate/s,Label\n1,1.5,BENIGN\n2,2.5,BENIGN\n'
    assert lint(write(tmp_path, content)) == []


def test_long_lists_are_cut_short() -> None:
    assert linting._listed([str(number) for number in range(10)]).endswith("'7' and 2 more")  # pyright: ignore[reportPrivateUsage]


def test_cli_exits_0_on_a_clean_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, CLEAN)
    assert main([str(path)]) == 0
    captured = capsys.readouterr()
    assert captured.out == f'{path}: no problems found\n'
    assert captured.err == '0 errors, 0 warnings\n'


def test_cli_exits_1_on_errors_and_cites_the_rule(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, b'Flow Duration,Rate/s,Label\n1,NaN,BENIGN\n2,2.5,Probe\n')
    assert main([str(path)]) == 1
    out = capsys.readouterr().out
    assert 'IDS002 error non-finite-values' in out
    assert 'see: ' in out
    assert 'https://doi.org/10.5220/0010774000003120' in out


def test_cli_warnings_only_fail_with_strict(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, CLEAN + b'1,1.5,BENIGN\n')
    assert main([str(path)]) == 0
    assert main([str(path), '--strict']) == 1
    assert '0 errors, 1 warnings' in capsys.readouterr().err


@pytest.mark.usefixtures('synthetic_registry')
def test_cli_release_option_checks_the_labels(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, CLEAN.replace(b'Probe', b'Mystery'))
    assert main([str(path)]) == 0
    assert main([str(path), '--release', 'synthetic', 'v1']) == 1
    assert "does not define: 'Mystery'" in capsys.readouterr().out


@pytest.mark.usefixtures('synthetic_registry')
def test_cli_release_option_needs_a_release_with_labels(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = write(tmp_path, CLEAN)
    assert main([str(path), '--release', 'synthetic', 'empty']) == 2
    assert main([str(path), '--release', 'synthetic', 'nope']) == 2
    err = capsys.readouterr().err
    assert 'no label strings are recorded' in err
    assert 'unknown version' in err


def test_cli_lists_the_rules(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(['--rules']) == 0
    out = capsys.readouterr().out
    for rule in RULES:
        assert f'{rule.id} {rule.name} ({rule.severity})' in out


def test_cli_reports_a_missing_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(tmp_path / 'absent.csv')]) == 2
    assert 'ids-lint:' in capsys.readouterr().err


def test_cli_needs_a_file() -> None:
    with pytest.raises(SystemExit) as raised:
        _ = main([])
    assert raised.value.code == 2


def test_the_readme_rule_table_matches_the_rules() -> None:
    readme = (Path(__file__).parent.parent / 'README.md').read_text(encoding='utf-8')
    table = readme.split('<!-- rules:start -->')[1].split('<!-- rules:end -->')[0]
    rows = [line for line in table.strip().splitlines()[2:] if line]
    assert len(rows) == len(RULES)
    for row, rule in zip(rows, RULES, strict=True):
        cells = [cell.strip() for cell in row.strip('|').split('|')]
        assert cells[:4] == [rule.id, rule.name, rule.severity, rule.explanation]
        assert re.findall(r'\((https://[^)]+)\)', cells[4]) == [source.url for source in rule.sources]
