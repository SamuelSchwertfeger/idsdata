# idsdata

Load intrusion-detection datasets by name and version, check them against recorded SHA-256 hashes, and get the right citation. `ids-lint` flags known quality problems in a dataset CSV file.

Papers that say "we used CIC-IDS2017" can mean several different files. `idsdata` makes the version part of the name, and refuses to load a file whose hash does not match.

## Install

`idsdata` is not on PyPI yet. Install it from the repository:

```console
pip install git+https://github.com/SamuelSchwertfeger/idsdata
```

It needs Python 3.10 or newer and installs pandas and pyarrow.

## Quickstart

```console
idsdata list
idsdata info cic-ids2017 engelen2021
idsdata download cic-ids2017 engelen2021
idsdata verify cic-ids2017 engelen2021
```

```python
import idsdata

flows = idsdata.load('cic-ids2017', 'engelen2021')
print(flows.shape)  # (2100814, 88)
print(flows['label'].value_counts())
print(idsdata.cite('cic-ids2017', 'engelen2021'))
```

`load` keeps every row and every value as it is in the source files. It gives the columns clean names (`Flow Bytes/s` becomes `flow_bytes_s`), keeps the source label as `label_raw`, and adds four columns:

| column | meaning |
|---|---|
| `label` | the label in lower case with underscores |
| `is_attack` | `True` for attack flows |
| `is_attempted` | `True` for flows the corrected release marks as "Attempted": part of an attack class, but with no malicious payload. These have `is_attack == False`. |
| `source_file` | the file the row came from |

Keeping "Attempted" flows out of `is_attack` is a choice this package makes, following the corrected release. It means `is_attack` and the class name can disagree: a `dos_hulk_attempted` row has `is_attack == False`. Decide what you want before training a binary classifier:

```python
flows = flows[~flows['is_attempted']]  # drop them
attack = flows['is_attack'] | flows['is_attempted']  # or count them as attacks
```

The first load reads the CSV files and writes a parquet cache next to them. Later loads read the cache.

## Datasets

| name | version | what it is | how you get it |
|---|---|---|---|
| `cic-ids2017` | `engelen2021` | Corrected flows and labels by Engelen, Rimmer and Joosen | `idsdata download`, or by hand from the authors' page |
| `cic-ids2017` | `original` | The original release from the Canadian Institute for Cybersecurity | By hand, through the request form on the publisher's page |

No file hashes are recorded for `original` yet, so it cannot be verified or loaded. `idsdata info cic-ids2017 original` prints where to get it and how to cite it.

## Data policy

- The package contains no dataset files and this repository will never contain any.
- Nothing is mirrored. Files come from the official host, or you download them yourself.
- `idsdata download` works only where the host offers a direct link. It prints the terms and asks before it fetches anything (`--yes` skips the question).
- A release behind a request form is never fetched by the package. You fill in the form and place the files; the package checks them.
- Every recorded hash was computed from a real download, and the registry records the date of that download. If the host replaces a file, verification fails and says so. It also fails when a table is missing and the archive it comes from is not there.

Files are kept in `~/.cache/idsdata/<name>/<version>/`. Set `IDSDATA_DIR` or pass `--data-dir` to use another place. `idsdata where NAME VERSION` prints the directory.

## How to cite

Cite the papers behind the data you use. This prints the BibTeX entries:

```console
idsdata cite cic-ids2017 engelen2021
```

For `engelen2021` that is the paper that corrected the dataset and the paper that introduced it:

- G. Engelen, V. Rimmer and W. Joosen, "Troubleshooting an Intrusion Detection Dataset: the CICIDS2017 Case Study", 2021 IEEE Security and Privacy Workshops (SPW), 2021. https://doi.org/10.1109/SPW53761.2021.00009
- I. Sharafaldin, A. Habibi Lashkari and A. Ghorbani, "Toward Generating a New Intrusion Detection Dataset and Intrusion Traffic Characterization", ICISSP 2018. https://doi.org/10.5220/0006639801080116

## ids-lint

```console
ids-lint Friday-WorkingHours.csv
ids-lint --release cic-ids2017 engelen2021 *.csv
ids-lint --rules
```

The exit status is 1 when a rule of severity `error` fires. With `--strict`, warnings count as well. `--release` also checks that every label string in the file belongs to that release.

<!-- rules:start -->
| id | rule | severity | what it flags | source |
|---|---|---|---|---|
| IDS001 | duplicated-column-names | error | Two columns share a name, so readers rename or overwrite one of them without saying so. | [Engelen et al., documentation](https://intrusion-detection.distrinet-research.be/WTMC2021/extended_doc.html) |
| IDS002 | non-finite-values | error | Missing, NaN or infinite feature values stop most learners or get dropped along the way. | [Rosay et al. 2022](https://doi.org/10.5220/0010774000003120) |
| IDS003 | label-strings | error | Missing or unknown label strings lose rows or split one class into several. | [Engelen et al. 2021](https://doi.org/10.1109/SPW53761.2021.00009), [Flood et al. 2024](https://doi.org/10.1109/EuroSP60621.2024.00042) |
| IDS004 | duplicate-rows | warn | Rows that repeat exactly can end up on both sides of a train/test split. | [Flood et al. 2024](https://doi.org/10.1109/EuroSP60621.2024.00042) |
| IDS005 | identifier-columns | warn | Flow ids, addresses, ports and timestamps describe the capture, and a model can learn them as a shortcut. | [Engelen et al. 2021](https://doi.org/10.1109/SPW53761.2021.00009), [D'hooge et al. 2022](https://doi.org/10.1007/978-3-031-09484-2_2) |
| IDS006 | constant-columns | warn | A column that holds a single value carries no information. | [Rosay et al. 2022](https://doi.org/10.5220/0010774000003120) |
<!-- rules:end -->

`ids-lint --rules` prints the full reference for each source. The source of IDS001 is the authors' documentation page, which is not peer reviewed. Flood et al. describe near-duplicate flows; IDS004 reports only exact repeats. The sources of IDS003 describe flows that carry the wrong label; IDS003 can only see label strings that are missing or that a release does not define.

The linter reports and changes nothing. A warning is a prompt to decide, and what to do with the flagged rows or columns is up to you.

## Not in this version

- Train/test splits. The split design is still open.
- Checksums for the `original` release.
- Other datasets.

## Acknowledgements

The CI setup is adapted from [DFAIR-LAB-Augusta/XSecIoT](https://github.com/DFAIR-LAB-Augusta/XSecIoT) (Seth Barrett).
