"""Static metadata for every dataset release idsdata knows about.

Nothing here is guessed. A file entry is only added with a SHA-256 computed
from a real download, so a release can exist with an empty file list.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


class UnknownDatasetError(LookupError):
    """Raised when a dataset name or version is not in the registry."""


@dataclass(frozen=True)
class Citation:
    key: str
    authors: tuple[str, ...]
    title: str
    booktitle: str
    publisher: str
    year: int
    pages: str
    doi: str

    def bibtex(self) -> str:
        fields = {
            'author': ' and '.join(self.authors),
            'title': '{' + self.title + '}',
            'booktitle': self.booktitle,
            'publisher': self.publisher,
            'year': str(self.year),
            'pages': self.pages.replace('-', '--'),
            'doi': self.doi,
        }
        width = max(len(name) for name in fields)
        lines = [f'  {name.ljust(width)} = {{{value}}},' for name, value in fields.items()]
        return '\n'.join([f'@inproceedings{{{self.key},', *lines, '}'])


@dataclass(frozen=True)
class FileEntry:
    name: str
    sha256: str
    size: int


@dataclass(frozen=True)
class Release:
    name: str
    version: str
    title: str
    summary: str
    homepage: str
    download_page: str
    access: Literal['form', 'direct']
    terms: str
    citations: tuple[Citation, ...]
    files: tuple[FileEntry, ...] = ()


SHARAFALDIN_2018 = Citation(
    key='sharafaldin2018toward',
    authors=('Sharafaldin, Iman', 'Habibi Lashkari, Arash', 'Ghorbani, Ali A.'),
    title='Toward Generating a New Intrusion Detection Dataset and Intrusion Traffic Characterization',
    booktitle='Proceedings of the 4th International Conference on Information Systems Security and Privacy',
    publisher='SCITEPRESS - Science and Technology Publications',
    year=2018,
    pages='108-116',
    doi='10.5220/0006639801080116',
)

ENGELEN_2021 = Citation(
    key='engelen2021troubleshooting',
    authors=('Engelen, Gints', 'Rimmer, Vera', 'Joosen, Wouter'),
    title='Troubleshooting an Intrusion Detection Dataset: the CICIDS2017 Case Study',
    booktitle='2021 IEEE Security and Privacy Workshops (SPW)',
    publisher='IEEE',
    year=2021,
    pages='7-12',
    doi='10.1109/SPW53761.2021.00009',
)

_RELEASES = (
    Release(
        name='cic-ids2017',
        version='original',
        title='CIC-IDS2017',
        summary='Original release from the Canadian Institute for Cybersecurity, University of New Brunswick.',
        homepage='https://www.unb.ca/cic/datasets/ids-2017.html',
        download_page='http://cicresearch.ca/CICDataset/CIC-IDS-2017/',
        access='form',
        terms=(
            'No licence is stated. The publisher makes the dataset publicly available for researchers '
            'and asks users to cite the related paper.'
        ),
        citations=(SHARAFALDIN_2018,),
    ),
    Release(
        name='cic-ids2017',
        version='engelen2021',
        title='CIC-IDS2017, corrected by Engelen, Rimmer and Joosen (2021)',
        summary='Corrected flows and labels from the DistriNet research group, KU Leuven.',
        homepage='https://intrusion-detection.distrinet-research.be/WTMC2021/',
        download_page='https://intrusion-detection.distrinet-research.be/WTMC2021/tools_datasets.html',
        access='direct',
        terms=(
            'No licence is stated. The authors ask users to cite their paper. '
            'The data is derived from CIC-IDS2017, so the original paper is cited as well.'
        ),
        citations=(ENGELEN_2021, SHARAFALDIN_2018),
    ),
)

REGISTRY: dict[tuple[str, str], Release] = {(release.name, release.version): release for release in _RELEASES}


def get(name: str, version: str) -> Release:
    try:
        return REGISTRY[name, version]
    except KeyError:
        names = sorted({known_name for known_name, _ in REGISTRY})
        if name not in names:
            raise UnknownDatasetError(f'unknown dataset {name!r}; known datasets: {", ".join(names)}') from None
        versions = [known_version for known_name, known_version in REGISTRY if known_name == name]
        raise UnknownDatasetError(
            f'unknown version {version!r} of {name}; known versions: {", ".join(versions)}'
        ) from None
