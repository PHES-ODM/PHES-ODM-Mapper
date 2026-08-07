# <img src="docs/img/ODM-logo.png" align="right" alt="" width="180"/> PHES-ODM Mapper

<!-- badges: start -->
[![lint.yaml](https://github.com/PHES-ODM/PHES-ODM-Mapper/actions/workflows/lint.yaml/badge.svg)](https://github.com/PHES-ODM/PHES-ODM-Mapper/actions/workflows/lint.yaml)
[![pytest.yaml](https://github.com/PHES-ODM/PHES-ODM-Mapper/actions/workflows/pytest.yaml/badge.svg)](https://github.com/PHES-ODM/PHES-ODM-Mapper/actions/workflows/pytest.yaml)
<!-- badges: end -->

## Important Notice

This repository currently uses custom features in
[LinkML-Map](https://github.com/linkml/linkml-map) that have not yet been added
to a branch of the LinkML-Map repository. These new features will be added and
merged soon. As such, the PHES-ODM-Mapper will not work unless you have access
to these changes. Please contact [mwellman@ohri.ca](mailto:mwellman@ohri.ca)
for questions.

## Introduction

The PHES-ODM Mapper converts wastewater surveillance data between reporting
formats and the [Public Health Environmental Surveillance Open Data Model
(PHES-ODM)](https://phes-odm.org). You give it your existing data files, tell it
which conversion to perform, and it writes a set of CSV files in the target
format with the tables linked together by generated primary and foreign keys.

Each conversion is defined by a **module** — a directory of schemas, mapping
rules, filters, and ID-generation code. Four modules are built in, and you can
create your own for formats that are not covered.

## Installation

Install with `pip` directly from GitHub:

```console
pip install git+https://github.com/PHES-ODM/PHES-ODM-Mapper.git
```

If that does not work, try over SSH:

```console
pip install git+ssh://git@github.com/PHES-ODM/PHES-ODM-Mapper.git
```

If you already have the Mapper installed, uninstall it first with `pip
uninstall odm-map`. To set up a development environment instead, see
[CONTRIBUTING.md](CONTRIBUTING.md).

Installing makes the `odm-map` command available.

## Supported Mappings

| Module | Source Format | Target Format |
| :------------------- | :------------ | :------------ |
| `odm-v1-to-v2` | ODM v1 | ODM v2 / v3 |
| `nwss-reporting-to-v2` | NWSS Reporting | ODM v2 / v3 |
| `pha4ge-to-v2` | PHA4GE | ODM v2 / v3 |
| `odm-v3-wide-to-long` | ODM v3 wide format | ODM v3 long format |

Every mapping is run with the same command shape — pick the module with
`--module`, choose where the output goes with `--output-dir`, and list the input
files or directories last:

```console
odm-map --module <module-name> --output-dir <output-dir> <input> [<input> ...]
```

The Mapper works out which source table each input file belongs to from the file
name (or, for Excel workbooks, from each sheet tab name), so the sections below
differ only in the module name and in what the input files must be called. See
[How the input files are matched to
tables](docs/how_to.md#choose-which-files-and-tables-to-map) if your files are
named differently.

### ODM v1 → ODM v2 / v3

```console
odm-map \
    --module odm-v1-to-v2 \
    --output-dir "output/odm-v1-to-v2" \
    "path/to/odm-v1-data"
```

The input directory holds one file per ODM v1 table, named after the table:
`Sample`, `WWMeasure`, `Site`, `SiteMeasure`, `Reporter`, `Lab`, `AssayMethod`,
`Instrument`, `Polygon`, `CovidPublicHealthData`, and `Lookup`. Only the tables
you have are required — for example, `Sample.csv` and `WWMeasure.csv` alone are
enough to produce measures and samples in the output.

### NWSS Reporting → ODM v2 / v3

```console
odm-map \
    --module nwss-reporting-to-v2 \
    --output-dir "output/nwss-reporting-to-v2" \
    "path/to/nwss.csv"
```

NWSS Reporting is a single-table format, and the table is named `nwss`, so the
input file (or Excel sheet) must be named `nwss`.

### PHA4GE → ODM v2 / v3

```console
odm-map \
    --module pha4ge-to-v2 \
    --output-dir "output/pha4ge-to-v2" \
    "path/to/PHA4GE.xlsx"
```

PHA4GE is also a single-table format, with the table named `PHA4GE`, so the
input file or sheet must be named `PHA4GE`.

### ODM v3 wide → ODM v3 long

```console
odm-map \
    --module odm-v3-wide-to-long \
    --output-dir "output/odm-v3-wide-to-long" \
    "path/to/odm_wide.xlsx"
```

The wide format is a single table named `odm_wide`, in which each row carries
many measures across its columns. The column names encode which measure, unit,
and compartment each value belongs to; that naming scheme is described in
[wide_to_long_spec.md](docs/wide_to_long_spec.md).

### A custom mapping

For a module you have built yourself, replace `--module` with `--module-path`
and point it at the module directory (or a ZIP file of it):

```console
odm-map \
    --module-path "path/to/my-module" \
    --output-dir "output/my-mapping" \
    "path/to/inputdata"
```

See [Create a custom module](docs/how_to.md#create-a-custom-module) to build
one.

## Documentation

The documentation is organized into four kinds of material. Start with the
tutorial if you have not run the Mapper before.

| | Document | Read it when you want to |
| :--- | :------- | :----------------------- |
| **Tutorial** | [tutorial.md](docs/tutorial.md) | Learn the Mapper by running a complete mapping on sample data, start to finish |
| **How-to guides** | [how_to.md](docs/how_to.md) | Accomplish a specific task: select input tables, run from Python, build a custom module, speed up or debug a run |
| **Reference** | [reference.md](docs/reference.md) | Look up an exact detail: command-line options, the Python API, or the module `config.yaml` |
| **Explanation** | [explanation.md](docs/explanation.md) | Understand how the Mapper works and why it is built this way |

Reference material for the individual parts of a module has its own documents:

| Document | Description |
| :------- | :---------- |
| [actions/](docs/actions/) | One document per pipeline action, plus [actions/README.md](docs/actions/README.md) for what applies to every action |
| [filters.md](docs/filters.md) | The filter file format and every filter operation |
| [id_generator.md](docs/id_generator.md) | The ID code and ID config files used to generate primary and foreign keys |
| [wide_to_long_spec.md](docs/wide_to_long_spec.md) | The wide-format column naming and expansion rules |

More database formats will be supported as needed. If you require help creating
a custom module, contact [mwellman@ohri.ca](mailto:mwellman@ohri.ca).

## Contributing

To set up a development environment, understand the codebase structure, or
submit a pull request, see [CONTRIBUTING.md](CONTRIBUTING.md).
