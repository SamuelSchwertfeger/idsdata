"""Command line interface: ``idsdata``."""

from __future__ import annotations

import argparse
import sys

from typing import TYPE_CHECKING

import idsdata

from idsdata import downloading, storage

if TYPE_CHECKING:
    from collections.abc import Sequence


class _Arguments(argparse.Namespace):
    command: str = ''
    name: str = ''
    version: str = ''
    data_dir: str | None = None
    yes: bool = False


def _add_release_arguments(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument('name', help='dataset name, for example cic-ids2017')
    _ = parser.add_argument('version', help='release version, for example engelen2021')


def _add_data_dir_argument(parser: argparse.ArgumentParser) -> None:
    _ = parser.add_argument(
        '--data-dir',
        help=f'data directory (default: ${storage.ENV_VAR}, else ~/.cache/idsdata)',
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog='idsdata', description=idsdata.__doc__)
    _ = parser.add_argument('--version', action='version', version=f'%(prog)s {idsdata.__version__}')
    commands = parser.add_subparsers(dest='command', required=True)

    _ = commands.add_parser('list', help='list known datasets and versions')
    _add_release_arguments(commands.add_parser('info', help='show where a release comes from and its terms'))
    _add_release_arguments(commands.add_parser('cite', help='print the BibTeX entries for a release'))
    for command, text in [
        ('where', 'print the directory a release is read from'),
        ('verify', 'check the files of a release against their recorded SHA-256'),
    ]:
        subparser = commands.add_parser(command, help=text)
        _add_release_arguments(subparser)
        _add_data_dir_argument(subparser)
    download = commands.add_parser('download', help='fetch a release from its official host, where that is allowed')
    _add_release_arguments(download)
    _add_data_dir_argument(download)
    _ = download.add_argument('--yes', action='store_true', help='do not ask before downloading')
    return parser


def _format_info(release: idsdata.Release) -> str:
    access = {
        'form': 'request form on the download page; download by hand',
        'direct': 'direct link on the download page',
    }[release.access]
    rows = [
        ('dataset', f'{release.name} {release.version}'),
        ('title', release.title),
        ('summary', release.summary),
        ('homepage', release.homepage),
        ('download', release.download_page),
        ('access', access),
        ('terms', release.terms),
        ('cite', ', '.join(f'doi:{citation.doi}' for citation in release.citations)),
        ('files', f'{len(release.files)} with a recorded SHA-256' if release.files else 'none recorded yet'),
    ]
    if release.retrieved:
        rows.append(('retrieved', release.retrieved))
    if release.notes:
        rows.append(('notes', release.notes))
    width = max(len(label) for label, _ in rows)
    return '\n'.join(f'{label.ljust(width)}  {value}' for label, value in rows)


def _confirmed() -> bool:
    try:
        answer = input('Download? [y/N] ')
    except EOFError:
        return False
    return answer.strip().lower() in {'y', 'yes'}


def _download(args: _Arguments) -> int:
    release = idsdata.info(args.name, args.version)
    directory = storage.release_dir(args.name, args.version, args.data_dir)
    if not downloading.downloadable(release):
        print(f'idsdata: {release.name} {release.version} has to be downloaded by hand.', file=sys.stderr)
        print(storage.pointer(release, directory), file=sys.stderr)
        return 1
    print(downloading.notice(release, directory))
    if not args.yes and not _confirmed():
        print('idsdata: nothing downloaded (pass --yes to skip this question)', file=sys.stderr)
        return 1
    for path in downloading.download(args.name, args.version, args.data_dir):
        print(f'ok  {path}')
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv, namespace=_Arguments())
    try:
        if args.command == 'list':
            for name, versions in idsdata.datasets().items():
                for version in versions:
                    print(f'{name} {version}')
        elif args.command == 'info':
            print(_format_info(idsdata.info(args.name, args.version)))
        elif args.command == 'cite':
            print(idsdata.cite(args.name, args.version))
        elif args.command == 'where':
            directory = storage.release_dir(args.name, args.version, args.data_dir)
            print(directory)
            if not directory.is_dir():
                print(storage.pointer(idsdata.info(args.name, args.version), directory), file=sys.stderr)
        elif args.command == 'verify':
            for path in idsdata.verify(args.name, args.version, args.data_dir):
                print(f'ok  {path}')
        elif args.command == 'download':
            return _download(args)
    except idsdata.UnknownDatasetError as error:
        print(f'idsdata: {error}', file=sys.stderr)
        return 2
    except (
        idsdata.ChecksumMismatchError,
        idsdata.ChecksumsUnavailableError,
        idsdata.DataNotFoundError,
        OSError,
    ) as error:
        print(f'idsdata: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
