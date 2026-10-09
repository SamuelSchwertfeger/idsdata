"""Named train/test splits of a release."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pandas as pd

from idsdata.loading import load
from idsdata.registry import get as get_release

if TYPE_CHECKING:
    import os

    from idsdata.model import Release

SPLITS = ('time', 'random')

# Both numbers are part of what a split name means. Changing either makes a different split.
TEST_PERCENT = 20
SEED = 0


def _latest(order: pd.Series, groups: list[pd.Series]) -> pd.Series:
    """Mark the last ``TEST_PERCENT`` percent of each group, in the order given, as test rows.

    Rows that tie in ``order`` keep the order they have in the frame. A group of
    two or more rows always gets at least one test row; a single row stays in train.
    """
    grouped = order.groupby(groups, sort=False)
    rank = grouped.rank(method='first').astype('int64')
    size = grouped.transform('size').astype('int64')
    test_rows = (size * TEST_PERCENT // 100).clip(lower=1).where(size > 1, 0)
    return rank > size - test_rows


def _time_mask(flows: pd.DataFrame, release: Release) -> pd.Series:
    if release.time_column is None or release.time_format is None:
        raise ValueError(f'no timestamp column is recorded for {release.name} {release.version}; use the random split')
    times = pd.to_datetime(flows[release.time_column], format=release.time_format)
    return _latest(times, [flows['source_file'], flows['label']])


def _random_mask(flows: pd.DataFrame) -> pd.Series:
    shuffled = pd.Series(range(len(flows)), index=flows.index).sample(frac=1, random_state=SEED)
    position = pd.Series(range(len(flows)), index=shuffled.index).reindex(flows.index)
    return _latest(position, [flows['label']])


def split(
    name: str,
    version: str,
    split: str = 'time',
    data_dir: str | os.PathLike[str] | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load a whole release and return it as ``(train, test)``.

    ``time``: for each class in each source file, the earliest 80% of the flows
    are train and the latest 20% are test. ``random``: 20% of each class, drawn
    with a fixed seed, is test. Rows keep the index and order ``load`` gives them.
    """
    release = get_release(name, version)
    if split not in SPLITS:
        raise ValueError(f'unknown split {split!r}; known splits: {", ".join(SPLITS)}')
    flows = load(name, version, data_dir)
    test = _time_mask(flows, release) if split == 'time' else _random_mask(flows)
    return flows.loc[~test, :], flows.loc[test, :]
