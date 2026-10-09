"""The record types the registry is built from."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal


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
    """One file of a release. ``archive`` names the archive a table is packed in."""

    name: str
    sha256: str
    size: int
    kind: Literal['archive', 'table'] = 'table'
    archive: str | None = None
    url: str | None = None
    rows: int | None = None


@dataclass(frozen=True)
class Column:
    """A column as named in the source file, its clean name and its Arrow type."""

    original: str
    name: str
    dtype: Literal['int64', 'double', 'string']


@dataclass(frozen=True)
class Label:
    """A label string as it appears in the source file and what it maps to."""

    raw: str
    label: str
    is_attack: bool
    is_attempted: bool = False


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
    columns: tuple[Column, ...] = ()
    labels: tuple[Label, ...] = ()
    retrieved: str | None = None
    notes: str = ''
