from __future__ import annotations

import dataclasses
import math
import re

from typing import TYPE_CHECKING

import pytest

import idsdata

from idsdata import loading, registry
from tests.conftest import MONDAY, TUESDAY, make_archive, make_release, place, register

if TYPE_CHECKING:
    from pathlib import Path

COLUMNS = ['flow_id', 'rate_s', 'count', 'label_raw', 'label', 'is_attack', 'is_attempted', 'source_file']


@pytest.mark.usefixtures('synthetic_registry')
def test_load_concatenates_every_file(data_dir: Path) -> None:
    _ = place(data_dir, 'v1', 'monday.csv')
    _ = place(data_dir, 'v1', 'tuesday.csv')
    frame = idsdata.load('synthetic', 'v1', data_dir)
    assert list(frame.columns) == COLUMNS
    assert frame['flow_id'].tolist() == ['a', 'b', 'c', 'd', 'e']
    assert frame['count'].tolist() == [1, 2, 3, 4, 5]
    assert frame['source_file'].tolist() == ['monday.csv'] * 3 + ['tuesday.csv'] * 2


@pytest.mark.usefixtures('synthetic_registry')
def test_load_keeps_raw_labels_and_adds_the_mapping(data_dir: Path) -> None:
    _ = place(data_dir, 'v1', 'monday.csv')
    _ = place(data_dir, 'v1', 'tuesday.csv')
    frame = idsdata.load('synthetic', 'v1', data_dir)
    assert frame['label_raw'].tolist() == ['BENIGN', 'BENIGN', 'Probe', 'Probe - Attempted', 'BENIGN']
    assert frame['label'].tolist() == ['benign', 'benign', 'probe', 'probe_attempted', 'benign']
    assert frame['is_attack'].tolist() == [False, False, True, False, False]
    assert frame['is_attempted'].tolist() == [False, False, False, True, False]


@pytest.mark.usefixtures('synthetic_registry')
def test_load_keeps_nan_and_infinite_values(data_dir: Path) -> None:
    _ = place(data_dir, 'v1', 'monday.csv')
    rates = idsdata.load('synthetic', 'v1', data_dir, files=['monday.csv'])['rate_s'].tolist()
    assert rates[0] == 1.5
    assert math.isnan(rates[1])
    assert math.isinf(rates[2])


@pytest.mark.usefixtures('synthetic_registry')
def test_load_can_read_some_files(data_dir: Path) -> None:
    _ = place(data_dir, 'v1', 'tuesday.csv')
    frame = idsdata.load('synthetic', 'v1', data_dir, files=['tuesday.csv'])
    assert frame['flow_id'].tolist() == ['d', 'e']


@pytest.mark.usefixtures('synthetic_registry')
def test_load_rejects_unknown_file_names(data_dir: Path) -> None:
    with pytest.raises(ValueError, match='known files: monday.csv, tuesday.csv'):
        _ = idsdata.load('synthetic', 'v1', data_dir, files=['archive.zip'])


@pytest.mark.usefixtures('synthetic_registry')
def test_load_extracts_tables_from_a_verified_archive(data_dir: Path) -> None:
    _ = place(data_dir, 'v1', 'archive.zip')
    frame = idsdata.load('synthetic', 'v1', data_dir)
    assert len(frame) == 5
    assert (data_dir / 'synthetic' / 'v1' / 'monday.csv').read_bytes() == MONDAY


@pytest.mark.usefixtures('synthetic_registry')
def test_load_does_not_extract_from_a_bad_archive(data_dir: Path) -> None:
    _ = place(data_dir, 'v1', 'archive.zip', make_archive({'monday.csv': b'evil', 'tuesday.csv': b'evil'}))
    with pytest.raises(idsdata.ChecksumMismatchError):
        _ = idsdata.load('synthetic', 'v1', data_dir)
    assert not (data_dir / 'synthetic' / 'v1' / 'monday.csv').exists()


@pytest.mark.usefixtures('synthetic_registry')
def test_load_rejects_a_modified_table(data_dir: Path) -> None:
    _ = place(data_dir, 'v1', 'monday.csv', MONDAY.replace(b'Probe', b'BENIGN'))
    with pytest.raises(idsdata.ChecksumMismatchError):
        _ = idsdata.load('synthetic', 'v1', data_dir, files=['monday.csv'])


@pytest.mark.usefixtures('synthetic_registry')
def test_load_without_files_points_to_the_source(data_dir: Path) -> None:
    _ = place(data_dir, 'v1', 'monday.csv')
    with pytest.raises(idsdata.DataNotFoundError) as raised:
        _ = idsdata.load('synthetic', 'v1', data_dir)
    assert 'missing: tuesday.csv' in str(raised.value)
    assert 'https://example.org/download' in str(raised.value)


@pytest.mark.usefixtures('synthetic_registry')
def test_load_needs_recorded_files(data_dir: Path) -> None:
    with pytest.raises(idsdata.ChecksumsUnavailableError, match='cannot be loaded'):
        _ = idsdata.load('synthetic', 'empty', data_dir)


@pytest.mark.usefixtures('synthetic_registry')
def test_load_writes_and_reuses_the_parquet_cache(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _ = place(data_dir, 'v1', 'monday.csv')
    _ = place(data_dir, 'v1', 'tuesday.csv')
    first = idsdata.load('synthetic', 'v1', data_dir)
    cached = sorted(path.name for path in (data_dir / 'synthetic' / 'v1' / 'cache').iterdir())
    assert len(cached) == 2
    assert all(re.fullmatch(r'(monday|tuesday)\.[0-9a-f]{12}\.[0-9a-f]{8}\.v1\.parquet', name) for name in cached)

    def fail(*_args: object) -> None:
        raise AssertionError('the CSV was read again')

    monkeypatch.setattr(loading, '_read_table', fail)
    second = idsdata.load('synthetic', 'v1', data_dir)
    assert second.equals(first)


def test_load_does_not_reuse_the_cache_after_the_label_mapping_changes(
    data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    release = make_release('v1', {'monday.csv': MONDAY, 'tuesday.csv': TUESDAY})
    register(monkeypatch, release)
    _ = place(data_dir, 'v1', 'monday.csv')
    _ = place(data_dir, 'v1', 'tuesday.csv')
    assert int(idsdata.load('synthetic', 'v1', data_dir)['is_attack'].sum()) == 1
    labels = tuple(dataclasses.replace(label, is_attack=label.raw != 'BENIGN') for label in release.labels)
    register(monkeypatch, dataclasses.replace(release, labels=labels))
    assert int(idsdata.load('synthetic', 'v1', data_dir)['is_attack'].sum()) == 2


def test_load_names_an_archive_that_lacks_a_table(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    archive = make_archive({'monday.csv': MONDAY})
    register(monkeypatch, make_release('v1', {'archive.zip': archive, 'monday.csv': MONDAY, 'tuesday.csv': TUESDAY}))
    _ = place(data_dir, 'v1', 'archive.zip', archive)
    with pytest.raises(ValueError, match='has no member named tuesday.csv'):
        _ = idsdata.load('synthetic', 'v1', data_dir)


def test_load_rejects_unexpected_columns(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = MONDAY.replace(b'Count', b'Total')
    register(monkeypatch, make_release('v1', {'monday.csv': content}))
    _ = place(data_dir, 'v1', 'monday.csv', content)
    with pytest.raises(ValueError, match='does not have the columns recorded'):
        _ = idsdata.load('synthetic', 'v1', data_dir)


def test_load_rejects_unknown_labels(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    content = MONDAY.replace(b'Probe', b'Mystery')
    register(monkeypatch, make_release('v1', {'monday.csv': content}))
    _ = place(data_dir, 'v1', 'monday.csv', content)
    with pytest.raises(ValueError, match=r"not in the registry: \['Mystery'\]"):
        _ = idsdata.load('synthetic', 'v1', data_dir)


def test_recorded_releases_are_consistent() -> None:
    for release in registry.REGISTRY.values():
        if not release.files:
            assert not release.columns
            assert not release.labels
            continue
        names = [entry.name for entry in release.files]
        assert len(set(names)) == len(names)
        assert release.retrieved
        for entry in release.files:
            assert (entry.archive is None) or (entry.archive in names)
        clean = [column.name for column in release.columns]
        assert len(set(clean)) == len(clean)
        assert clean[-1] == 'label_raw'
        repeats: dict[str, int] = {}
        for column in release.columns[:-1]:
            # A column name that repeats in the source gets a number, like pandas gives it.
            base = re.sub(r'[^0-9a-z]+', '_', column.original.strip().lower()).strip('_')
            seen = repeats.get(base, 0)
            assert column.name == (f'{base}_{seen}' if seen else base)
            repeats[base] = seen + 1
        types = {column.original: column.dtype for column in release.columns}
        assert all(types[column.original] == column.dtype for column in release.columns)
        for entry in release.files:
            assert entry.member is None or entry.member.endswith('/' + entry.name)
        raw = [label.raw for label in release.labels]
        assert len(set(raw)) == len(raw)
        assert not any(label.is_attack and label.is_attempted for label in release.labels)
