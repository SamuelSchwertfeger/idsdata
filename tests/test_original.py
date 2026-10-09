"""What the loader needs for files shaped like the original CIC-IDS2017 release."""

from __future__ import annotations

import dataclasses
import hashlib

from typing import TYPE_CHECKING

import pytest

import idsdata

from idsdata import loading
from idsdata.model import Column, FileEntry, Label
from tests.conftest import make_archive, make_release, register

if TYPE_CHECKING:
    from pathlib import Path

    from idsdata.model import Release

# Everything below is made up for the tests. The header repeats a name, the
# names start with a space, one label holds byte 0x96 and two lines are blank.
TABLE = b'Flow ID, Size, Rate, Size, Label\r\na,1,1.0,1,BENIGN\r\nb,2,2.0,2,Web Attack \x96 XSS\r\n,,,,\r\n,,,,\r\n'
COLUMNS = (
    Column('Flow ID', 'flow_id', 'string'),
    Column(' Size', 'size', 'int64'),
    Column(' Rate', 'rate', 'double'),
    Column(' Size', 'size_1', 'int64'),
    Column(' Label', 'label_raw', 'string'),
)
LABELS = (
    Label('BENIGN', 'benign', is_attack=False),
    Label('Web Attack \u2013 XSS', 'web_attack_xss', is_attack=True),
)
MEMBER = 'Some Folder /day.csv'


def shaped(table: bytes = TABLE, *, rows: int | None = 2, blank_rows: int = 2, encoding: str = 'cp1252') -> Release:
    archive = make_archive({MEMBER: table})
    files = (
        FileEntry('archive.zip', hashlib.sha256(archive).hexdigest(), len(archive), kind='archive'),
        FileEntry(
            'day.csv',
            hashlib.sha256(table).hexdigest(),
            len(table),
            archive='archive.zip',
            member=MEMBER,
            rows=rows,
            blank_rows=blank_rows,
        ),
    )
    release = make_release('v1', {'archive.zip': archive}, form=True)
    return dataclasses.replace(release, files=files, columns=COLUMNS, labels=LABELS, encoding=encoding)


def place_archive(data_dir: Path, table: bytes = TABLE) -> None:
    directory = data_dir / 'synthetic' / 'v1'
    directory.mkdir(parents=True)
    _ = (directory / 'archive.zip').write_bytes(make_archive({MEMBER: table}))


def test_load_reads_a_table_from_a_folder_inside_the_archive(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    register(monkeypatch, shaped())
    place_archive(data_dir)
    flows = idsdata.load('synthetic', 'v1', data_dir)
    assert (data_dir / 'synthetic' / 'v1' / 'day.csv').read_bytes() == TABLE
    assert flows['source_file'].tolist() == ['day.csv', 'day.csv']


def test_load_keeps_both_columns_that_share_a_name(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    register(monkeypatch, shaped())
    place_archive(data_dir)
    flows = idsdata.load('synthetic', 'v1', data_dir)
    assert list(flows.columns[:5]) == ['flow_id', 'size', 'rate', 'size_1', 'label_raw']
    assert flows['size'].tolist() == [1, 2]
    assert flows['size_1'].tolist() == [1, 2]
    assert str(flows['size'].dtype) == 'int64'


def test_load_decodes_with_the_recorded_encoding(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    register(monkeypatch, shaped())
    place_archive(data_dir)
    flows = idsdata.load('synthetic', 'v1', data_dir)
    assert flows['label_raw'].tolist() == ['BENIGN', 'Web Attack \u2013 XSS']
    assert flows['label'].tolist() == ['benign', 'web_attack_xss']


def test_load_leaves_out_the_recorded_blank_lines(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    register(monkeypatch, shaped())
    place_archive(data_dir)
    assert len(idsdata.load('synthetic', 'v1', data_dir)) == 2


def test_load_rejects_blank_lines_the_registry_does_not_record(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    register(monkeypatch, shaped(blank_rows=0))
    place_archive(data_dir)
    with pytest.raises(ValueError, match='has 2 lines without values; the registry records 0'):
        _ = idsdata.load('synthetic', 'v1', data_dir)


def test_load_rejects_an_empty_label_on_a_line_with_values(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    table = TABLE.replace(b',,,,\r\n,,,,\r\n', b',,,,\r\nc,3,3.0,3,\r\n')
    register(monkeypatch, shaped(table))
    place_archive(data_dir, table)
    with pytest.raises(ValueError, match='rows with an empty label that hold other values'):
        _ = idsdata.load('synthetic', 'v1', data_dir)


def test_load_rejects_a_row_count_the_registry_does_not_record(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    register(monkeypatch, shaped(rows=3))
    place_archive(data_dir)
    with pytest.raises(ValueError, match='has 2 rows; the registry records 3'):
        _ = idsdata.load('synthetic', 'v1', data_dir)


def test_the_original_versions_record_the_same_flows() -> None:
    flows = idsdata.info('cic-ids2017', 'original-flows')
    ml = idsdata.info('cic-ids2017', 'original-ml')
    rows = {}
    for release in (flows, ml):
        tables = [entry for entry in release.files if entry.kind == 'table']
        assert len(tables) == 8
        assert all(entry.archive and entry.member for entry in tables)
        rows[release.version] = {entry.name: entry.rows for entry in tables}
        assert release.time_column is None
    assert rows['original-flows'] == rows['original-ml']
    assert sum(count or 0 for count in rows['original-ml'].values()) == 2830743
    assert {label.label for label in flows.labels} == {label.label for label in ml.labels}


def test_the_cache_name_depends_on_a_recorded_encoding() -> None:
    release = shaped()
    assert loading._mapping_key(release) != loading._mapping_key(dataclasses.replace(release, encoding='utf8'))  # pyright: ignore[reportPrivateUsage]
