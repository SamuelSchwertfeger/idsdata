import re

import pytest

import idsdata

from idsdata import registry

RELEASES = [('cic-ids2017', 'original'), ('cic-ids2017', 'engelen2021')]


def test_datasets_lists_both_versions() -> None:
    assert idsdata.datasets() == {'cic-ids2017': ('original', 'engelen2021')}


@pytest.mark.parametrize(['name', 'version'], RELEASES)
def test_info_returns_matching_release(name: str, version: str) -> None:
    release = idsdata.info(name, version)
    assert (release.name, release.version) == (name, version)
    assert release.homepage.startswith('https://')
    assert release.download_page.startswith(('http://', 'https://'))
    assert release.terms
    assert release.citations


def test_access_modes() -> None:
    assert idsdata.info('cic-ids2017', 'original').access == 'form'
    assert idsdata.info('cic-ids2017', 'engelen2021').access == 'direct'


def test_no_file_entry_without_a_real_hash() -> None:
    for release in registry.REGISTRY.values():
        for entry in release.files:
            assert re.fullmatch(r'[0-9a-f]{64}', entry.sha256), (release.name, release.version, entry.name)
            assert entry.size > 0


def test_unknown_dataset_names_the_known_ones() -> None:
    with pytest.raises(idsdata.UnknownDatasetError, match='known datasets: cic-ids2017'):
        _ = idsdata.info('nsl-kdd', 'original')


def test_unknown_version_names_the_known_ones() -> None:
    with pytest.raises(idsdata.UnknownDatasetError, match='known versions: original, engelen2021'):
        _ = idsdata.info('cic-ids2017', 'liu2022')


def test_cite_original() -> None:
    bibtex = idsdata.cite('cic-ids2017', 'original')
    assert bibtex.startswith('@inproceedings{sharafaldin2018toward,')
    assert '10.5220/0006639801080116' in bibtex
    assert 'pages     = {108--116},' in bibtex
    assert bibtex.count('@inproceedings') == 1


def test_cite_engelen_includes_the_original_paper() -> None:
    bibtex = idsdata.cite('cic-ids2017', 'engelen2021')
    assert bibtex.startswith('@inproceedings{engelen2021troubleshooting,')
    assert '10.1109/SPW53761.2021.00009' in bibtex
    assert '10.5220/0006639801080116' in bibtex
    assert bibtex.count('@inproceedings') == 2


@pytest.mark.parametrize(['name', 'version'], RELEASES)
def test_bibtex_braces_balance(name: str, version: str) -> None:
    bibtex = idsdata.cite(name, version)
    assert bibtex.count('{') == bibtex.count('}')
    assert bibtex.rstrip().endswith('}')
