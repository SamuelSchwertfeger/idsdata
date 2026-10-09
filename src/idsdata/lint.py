"""``ids-lint``: flag known quality problems in an intrusion-detection CSV file."""

from __future__ import annotations

import argparse
import csv
import re
import sys

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pandas as pd

from idsdata.registry import UnknownDatasetError
from idsdata.registry import get as get_release

if TYPE_CHECKING:
    import os

    from collections.abc import Sequence

# Clean names of columns that identify a flow or its capture rather than describe its behaviour.
IDENTIFIER_COLUMNS = frozenset({
    'flow_id',
    'src_ip',
    'source_ip',
    'dst_ip',
    'destination_ip',
    'src_port',
    'source_port',
    'dst_port',
    'destination_port',
    'timestamp',
})

_SHOWN = 8


@dataclass(frozen=True)
class Source:
    """Where the problem a rule looks for is documented."""

    authors: str
    title: str
    where: str
    url: str

    def text(self) -> str:
        return f'{self.authors}, "{self.title}", {self.where}. {self.url}'


@dataclass(frozen=True)
class Rule:
    id: str
    name: str
    severity: Literal['error', 'warn']
    explanation: str
    sources: tuple[Source, ...]


@dataclass(frozen=True)
class Finding:
    rule: Rule
    detail: str


_ENGELEN_2021 = Source(
    'Engelen, Rimmer and Joosen',
    'Troubleshooting an Intrusion Detection Dataset: the CICIDS2017 Case Study',
    'IEEE Security and Privacy Workshops, 2021, section III',
    'https://doi.org/10.1109/SPW53761.2021.00009',
)
_ENGELEN_2021_DOCUMENTATION = Source(
    'Engelen, Rimmer and Joosen',
    'Extended documentation of the 2021 paper',
    'web page, not peer reviewed, section "Duplicate Fwd Header Length"',
    'https://intrusion-detection.distrinet-research.be/WTMC2021/extended_doc.html',
)
_ROSAY_2022 = Source(
    'Rosay, Cheval, Carlier and Leroux',
    'Network Intrusion Detection: A Comprehensive Analysis of CIC-IDS2017',
    'ICISSP 2022, section 6.1.1',
    'https://doi.org/10.5220/0010774000003120',
)
_DHOOGE_2022 = Source(
    "D'hooge, Verkerken, Volckaert, Wauters and De Turck",
    'Establishing the Contaminating Effect of Metadata Feature Inclusion in Machine-Learned Network Intrusion Detection Models',
    'DIMVA 2022',
    'https://doi.org/10.1007/978-3-031-09484-2_2',
)
_FLOOD_2024 = Source(
    'Flood, Engelen, Aspinall and Desmet',
    'Bad Design Smells in Benchmark NIDS Datasets',
    'IEEE EuroS&P 2024, on highly repetitive and mislabelled flows',
    'https://doi.org/10.1109/EuroSP60621.2024.00042',
)

RULES: tuple[Rule, ...] = (
    Rule(
        'IDS001',
        'duplicated-column-names',
        'error',
        'Two columns share a name, so readers rename or overwrite one of them without saying so.',
        (_ENGELEN_2021_DOCUMENTATION,),
    ),
    Rule(
        'IDS002',
        'non-finite-values',
        'error',
        'Missing, NaN or infinite feature values stop most learners or get dropped along the way.',
        (_ROSAY_2022,),
    ),
    Rule(
        'IDS003',
        'label-strings',
        'error',
        'Missing or unknown label strings lose rows or split one class into several.',
        (_ENGELEN_2021, _FLOOD_2024),
    ),
    Rule(
        'IDS004',
        'duplicate-rows',
        'warn',
        'Rows that repeat exactly can end up on both sides of a train/test split.',
        (_FLOOD_2024,),
    ),
    Rule(
        'IDS005',
        'identifier-columns',
        'warn',
        'Flow ids, addresses, ports and timestamps describe the capture, and a model can learn them as a shortcut.',
        (_ENGELEN_2021, _DHOOGE_2022),
    ),
    Rule(
        'IDS006',
        'constant-columns',
        'warn',
        'A column that holds a single value carries no information.',
        (_ROSAY_2022,),
    ),
)
_BY_NAME = {rule.name: rule for rule in RULES}


def clean_name(column: str) -> str:
    """Lowercase a column name and turn every run of other characters into one underscore."""
    return re.sub(r'[^0-9a-z]+', '_', column.strip().lower()).strip('_')


def _listed(names: Sequence[str]) -> str:
    shown = ', '.join(repr(name) for name in names[:_SHOWN])
    return shown if len(names) <= _SHOWN else f'{shown} and {len(names) - _SHOWN} more'


def _read_header(path: Path, encoding: str) -> list[str]:
    with path.open(encoding=encoding, errors='replace', newline='') as handle:
        return next(csv.reader(handle), [])


def _duplicated_column_names(header: list[str]) -> list[str]:
    counts = Counter(name.strip() for name in header)
    return [f'{name!r} appears {count} times' for name, count in counts.items() if count > 1]


def _positive(counts: pd.Series) -> dict[str, int]:
    """Per-column counts as a plain dict, without the zeros."""
    return {str(name): int(count) for name, count in counts.to_dict().items() if count}


def _non_finite(frame: pd.DataFrame, label_position: int | None) -> list[str]:
    details: list[str] = []
    features = frame.drop(columns=[] if label_position is None else [frame.columns[label_position]])
    missing = _positive(features.isna().sum())
    if missing:
        details.append(f'{sum(missing.values())} missing or NaN cells in {_listed(list(missing))}')
    numeric = features.select_dtypes('number')
    infinite = _positive(numeric.isin([float('inf'), float('-inf')]).sum())
    if infinite:
        details.append(f'{sum(infinite.values())} infinite cells in {_listed(list(infinite))}')
    return details


def _labels(values: pd.Series, known: frozenset[str] | None) -> list[str]:
    details: list[str] = []
    missing = int(values.isna().sum())
    if missing:
        details.append(f'{missing} rows have no label')
    seen = sorted(str(value) for value in values.dropna().unique())
    if known is not None:
        unknown = [value for value in seen if value not in known]
        if unknown:
            details.append(f'label strings the release does not define: {_listed(unknown)}')
    return details


def lint(
    path: str | os.PathLike[str], labels: Sequence[str] | None = None, encoding: str = 'utf-8-sig'
) -> list[Finding]:
    """Check one CSV file and return what was found, in rule order.

    ``labels`` is the set of label strings the file is allowed to contain. When
    it is left out, only missing labels are reported. Bytes that ``encoding``
    cannot decode are read as the replacement character.
    """
    source = Path(path)
    header = _read_header(source, encoding)
    frame = pd.read_csv(source, encoding=encoding, encoding_errors='replace', low_memory=False)
    label_positions = [position for position, name in enumerate(header) if clean_name(name) == 'label']
    label_position = label_positions[-1] if label_positions else None

    details: dict[str, list[str]] = {rule.name: [] for rule in RULES}
    details['duplicated-column-names'] = _duplicated_column_names(header)
    details['non-finite-values'] = _non_finite(frame, label_position)
    if label_position is None:
        details['label-strings'] = ['the file has no column named Label']
    else:
        known = None if labels is None else frozenset(labels)
        details['label-strings'] = _labels(frame.iloc[:, label_position], known)
    duplicates = int(frame.duplicated().sum())
    if duplicates:
        details['duplicate-rows'] = [f'{duplicates} of {len(frame)} rows repeat an earlier row exactly']
    identifiers = [name for name in header if clean_name(name) in IDENTIFIER_COLUMNS]
    if identifiers:
        details['identifier-columns'] = [f'present: {_listed(identifiers)}']
    if len(frame) > 1:
        single = frame.nunique(dropna=False) <= 1
        constant = [
            str(name)
            for position, name in enumerate(frame.columns)
            if bool(single.iloc[position]) and position != label_position
        ]
        if constant:
            details['constant-columns'] = [f'{len(constant)} columns hold a single value: {_listed(constant)}']
    return [Finding(_BY_NAME[name], detail) for name in details for detail in details[name]]


class _Arguments(argparse.Namespace):
    files: list[str]  # pyright: ignore[reportUninitializedInstanceVariable]
    strict: bool = False
    release: list[str] | None = None
    rules: bool = False


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='ids-lint', description=__doc__)
    _ = parser.add_argument('files', nargs='*', metavar='file.csv', help='CSV file to check')
    _ = parser.add_argument('--strict', action='store_true', help='exit non-zero on warnings too')
    _ = parser.add_argument(
        '--release',
        nargs=2,
        metavar=('NAME', 'VERSION'),
        help='also check the label strings against a release, for example cic-ids2017 engelen2021',
    )
    _ = parser.add_argument('--rules', action='store_true', help='list the rules with their sources and exit')
    return parser


def _format_rules() -> str:
    blocks: list[str] = []
    for rule in RULES:
        lines = [f'{rule.id} {rule.name} ({rule.severity})', f'  {rule.explanation}']
        lines.extend(f'  see: {source.text()}' for source in rule.sources)
        blocks.append('\n'.join(lines))
    return '\n\n'.join(blocks)


def _format_findings(path: str, findings: list[Finding]) -> str:
    if not findings:
        return f'{path}: no problems found'
    lines: list[str] = []
    for rule in RULES:
        mine = [finding for finding in findings if finding.rule is rule]
        if not mine:
            continue
        lines.append(f'{path}: {rule.id} {rule.severity} {rule.name}: {rule.explanation}')
        lines.extend(f'    {finding.detail}' for finding in mine)
        lines.extend(f'    see: {source.text()}' for source in rule.sources)
    return '\n'.join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv, namespace=_Arguments())
    if args.rules:
        print(_format_rules())
        return 0
    if not args.files:
        parser.error('give at least one CSV file')
    labels: list[str] | None = None
    encoding = 'utf-8-sig'
    if args.release is not None:
        try:
            release = get_release(args.release[0], args.release[1])
        except UnknownDatasetError as error:
            print(f'ids-lint: {error}', file=sys.stderr)
            return 2
        if not release.labels:
            print(f'ids-lint: no label strings are recorded for {release.name} {release.version} yet', file=sys.stderr)
            return 2
        labels = [label.raw for label in release.labels]
        encoding = 'utf-8-sig' if release.encoding == 'utf8' else release.encoding
    errors = warnings = 0
    for name in args.files:
        try:
            findings = lint(name, labels, encoding)
        except (OSError, ValueError) as error:
            print(f'ids-lint: {name}: {error}', file=sys.stderr)
            return 2
        # A label can hold a character the console cannot show; print it escaped instead of failing.
        console = sys.stdout.encoding or 'utf-8'
        print(_format_findings(name, findings).encode(console, 'backslashreplace').decode(console))
        errors += sum(finding.rule.severity == 'error' for finding in findings)
        warnings += sum(finding.rule.severity == 'warn' for finding in findings)
    print(f'{errors} errors, {warnings} warnings', file=sys.stderr)
    return 1 if errors or (args.strict and warnings) else 0
