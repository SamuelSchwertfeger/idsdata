from __future__ import annotations

import dataclasses

from typing import TYPE_CHECKING

import pytest

import idsdata

from idsdata.model import Column, Label
from idsdata.splitting import SPLITS
from tests.conftest import make_release, register

if TYPE_CHECKING:
    from pathlib import Path

# Everything below is made up for the tests. The row number is the Count column.
ONE = b"""Timestamp,Count,Label
03/07/2017 01:00:09 PM,0,BENIGN
03/07/2017 01:00:01 PM,1,BENIGN
03/07/2017 12:59:59 PM,2,BENIGN
03/07/2017 01:00:05 PM,3,Probe
03/07/2017 01:00:03 PM,4,BENIGN
03/07/2017 01:00:09 PM,5,BENIGN
03/07/2017 01:00:02 PM,6,Probe
03/07/2017 11:00:00 AM,7,BENIGN
03/07/2017 01:00:04 PM,8,BENIGN
03/07/2017 01:00:06 PM,9,BENIGN
03/07/2017 01:00:07 PM,10,BENIGN
03/07/2017 01:00:09 PM,11,BENIGN
03/07/2017 01:00:08 PM,12,Probe
03/07/2017 01:00:01 PM,13,Probe
03/07/2017 01:00:04 PM,14,Probe
03/07/2017 01:00:00 PM,15,Rare
"""
TWO = b"""Timestamp,Count,Label
04/07/2017 09:00:00 AM,16,BENIGN
04/07/2017 09:00:02 AM,17,BENIGN
04/07/2017 09:00:01 AM,18,BENIGN
"""
FILES = {'one.csv': ONE, 'two.csv': TWO}
COLUMNS = (
    Column('Timestamp', 'timestamp', 'string'),
    Column('Count', 'count', 'int64'),
    Column('Label', 'label_raw', 'string'),
)
PINNED = [0, 11, 12]
LABELS = (
    Label('BENIGN', 'benign', is_attack=False),
    Label('Probe', 'probe', is_attack=True),
    Label('Rare', 'rare', is_attack=True),
)


@pytest.fixture
def timed(data_dir: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A release with a timestamp column, placed in the data directory."""
    release = dataclasses.replace(
        make_release('v1', FILES),
        columns=COLUMNS,
        labels=LABELS,
        time_column='timestamp',
        time_format='%d/%m/%Y %I:%M:%S %p',
    )
    register(monkeypatch, release, dataclasses.replace(release, version='untimed', time_column=None, time_format=None))
    for version in ('v1', 'untimed'):
        directory = data_dir / 'synthetic' / version
        directory.mkdir(parents=True)
        for name, content in FILES.items():
            _ = (directory / name).write_bytes(content)
    return data_dir


def test_time_split_takes_the_latest_flows_of_each_class_in_each_file(timed: Path) -> None:
    train, test = idsdata.split('synthetic', 'v1', 'time', timed)
    # benign in one.csv: rows 0, 5 and 11 share the latest second and the first of them stays in train.
    # probe in one.csv: row 12 is the latest. benign in two.csv: three rows still give one test row.
    assert test['count'].tolist() == [5, 11, 12, 17]
    assert train['count'].tolist() == [0, 1, 2, 3, 4, 6, 7, 8, 9, 10, 13, 14, 15, 16, 18]


def test_time_is_the_default_split(timed: Path) -> None:
    assert idsdata.split('synthetic', 'v1', data_dir=timed)[1]['count'].tolist() == [5, 11, 12, 17]


def test_a_class_with_one_row_stays_in_train(timed: Path) -> None:
    for name in SPLITS:
        train, test = idsdata.split('synthetic', 'v1', name, timed)
        assert 'rare' in set(train['label'])
        assert 'rare' not in set(test['label'])


def test_random_split_is_stratified_and_repeatable(timed: Path) -> None:
    train, test = idsdata.split('synthetic', 'v1', 'random', timed)
    assert test['label'].value_counts().to_dict() == {'benign': 2, 'probe': 1}
    assert sorted([*train['count'], *test['count']]) == list(range(19))
    again = idsdata.split('synthetic', 'v1', 'random', timed)[1]
    assert again['count'].tolist() == test['count'].tolist()


def test_random_split_does_not_drift(timed: Path) -> None:
    # Pinned so that a change in pandas or in the code that moves rows between the sides is noticed.
    assert idsdata.split('synthetic', 'v1', 'random', timed)[1]['count'].tolist() == PINNED


def test_splits_keep_the_index_and_columns_of_load(timed: Path) -> None:
    flows = idsdata.load('synthetic', 'v1', timed)
    train, test = idsdata.split('synthetic', 'v1', 'time', timed)
    assert list(train.columns) == list(flows.columns)
    assert train.index.tolist() == train['count'].tolist()
    assert test.index.tolist() == test['count'].tolist()


def test_time_split_needs_a_recorded_timestamp_column(timed: Path) -> None:
    with pytest.raises(ValueError, match='no timestamp column is recorded for synthetic untimed'):
        _ = idsdata.split('synthetic', 'untimed', 'time', timed)
    assert len(idsdata.split('synthetic', 'untimed', 'random', timed)[1]) == 3


def test_unknown_split_names_are_rejected(timed: Path) -> None:
    with pytest.raises(ValueError, match='known splits: time, random'):
        _ = idsdata.split('synthetic', 'v1', 'chronological', timed)


def test_the_real_release_records_its_timestamp_column() -> None:
    release = idsdata.info('cic-ids2017', 'engelen2021')
    assert release.time_column in {column.name for column in release.columns}
    assert release.time_format
