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

This repository provides all tools required for mapping between various
wastewater reporting database formats and the [Public Health Environmental
Surveillance Open Data Model (PHES-ODM)](https://phes-odm.org). Conversion is
available for the following source formats:

| Module | Source Format | Target Format |
| :------- | :------------ | :------------- |
| `odm-v1-to-v2` | ODM v1 | ODM v2 / v3 |
| `nwss-reporting-to-v2` | NWSS Reporting | ODM v2 / v3 |
| `pha4ge-to-v2` | PHA4GE | ODM v2 / v3 |
| `odm-v3-wide-to-long` | ODM v3 wide format | ODM v3 long format |

More database formats will be provided as needed, and custom conversions can be
created. To add support for other databases, see [Custom
Modules](#custom-modules) below. If you require help in creating custom
modules, contact [mwellman@ohri.ca](mailto:mwellman@orhi.ca).

## Documentation

| Document | Description |
| :--------- | :----------- |
| [README.md](README.md) | Installation, CLI usage, and quick-start examples |
| [CONTRIBUTING.md](CONTRIBUTING.md) | Developer setup, code structure, and contribution guide |
| [custom_modules.md](docs/custom_modules.md) | Complete reference for creating custom conversion modules |
| [filters.md](docs/filters.md) | Filter system reference — how to remove unwanted rows |
| [id_generator.md](docs/id_generator.md) | ID generator reference — how to create primary and foreign keys |
| [merging_spec.md](docs/merging_spec.md) | Design spec for merging separately-mapped datasets (developer reference) |

## Access to Repository

Because this repository is currently private you may have issues installing or
cloning the Mapper. If you are having issues with installation, you may need to
generate an SSH key-pair. Follow these steps to generate an SSH key on Mac or
Linux:

1. Run the SSH agent:

    ```console
    eval $(ssh-agent -s)
    ```

2. Create the SSH key:

    ```console
    ssh-keygen -t rsa -C mapper
    ```

    When asked for a password, leave it blank.

3. From the files generated above, make sure the private key is added. Replace
   "privatekey" with the path to the private key file (the file generated from
   step 2 that has no extension):

    ```console
    ssh-add -K privatekey
    ```

4. Send the public key (the file with a .pub extension generated from step 2
   above) to [mwellman@ohri.ca](mailto:mwellman@orhi.ca).

Once you have sent the public key, you must wait for a reply to confirm that
you can continue with the installation. In the `pip install` step below, run
the one that starts with `pip install git+ssh`.

## Installation

If you will be running the Mapper but not working with the source code, follow
the instructions in this section. If you require the source code for
development, skip this section and follow the instructions in the next section
([Installation (For Development)](#installation-for-development)).

If you have previously installed the PHES-ODM-Mapper, uninstall it first with:

```console
pip uninstall odm-map
```

A full installation can be completed with the following command:

```console
pip install git+https://github.com/PHES-ODM/PHES-ODM-Mapper.git
```

If the above does not work, you can try:

```console
pip install git+ssh://git@github.com/PHES-ODM/PHES-ODM-Mapper.git
```

If neither `pip install` commands work, then follow the instructions in [Access
to Repository](#access-to-repository) to create an SSH key then retry the second
`pip install git+ssh` command.

## Installation (For Development)

Skip this section if you will not be developing for the PHES-ODM-Mapper library
(but be sure to follow the instructions in the above
[Installation](#installation) section).

To clone the repository, run the following on the command-line:

```console
git clone git@github.com:PHES-ODM/PHES-ODM-Mapper.git
cd PHES-ODM-Mapper
```

Create a virtual environment to use while running the Mapper:

```console
python -m venv .env
```

Activate the virtual environment on Linux/macOS:

```console
source .env/bin/activate
```

Or if you're running Windows:

```console
.env\Scripts\activate
```

If you previously installed the package, then uninstall it:

```console
pip uninstall odm-map
```

Install the odm-map package:

```console
pip install -e .
```

## Sample Data

Sample ODM v1 data is available if you require a sample dataset to run the
mapper on before you have your own data ready, or for testing purposes. The
data is provided by the [Ottawa Wastewater Surveillance Consortium on
Github](https://github.com/OntarioWastewaterSurveillanceConsortium/sars-cov-2-data).
Data can be downloaded manually on Github, or from the command-line using the
following:

```console
git clone git@github.com:OntarioWastewaterSurveillanceConsortium/sars-cov-2-data.git
```

Sample data from various locations can be found in the `CSV` directory. Record
the location of one of these directories for use as input to the mapper (eg.
"sars-cov-2-data/CSV/Ottawa").

## Command-Line Interface

A full mapping can be performed by using the command-line interface (CLI)
provided by the script [/odm_map/pipeline_cli.py](/odm_map/pipeline_cli.py) or
the installed `odm-map` command. If you installed the Mapper for development
purposes, be sure to always activate the virtual environment as described in
the [Installation (For Development)](#installation-for-development) section
above before running the script.

The general syntax for running the program is:

```console
odm-map [--options] input1 input2 input3 ...
```

The `input` arguments are either directories or files to map.

Below is an example to map ODM v1 data (found in the input directory
"sars-cov-2-data/CSV/Ottawa") to ODM v2 data. The results will be saved to the
directory "output/v2":

```console
odm-map \
    --module odm-v1-to-v2 \
    --output-dir "output/v2" \
    "sars-cov-2-data/CSV/Ottawa"
```

In the above example, the conversion module `odm-v1-to-v2` is used to convert
ODM v1 to ODM v2 data. All valid data files (csv, txt, tsv, yaml/yml, xlsx) in
the directory "sars-cov-2-data/CSV/Ottawa" will be mapped. For Excel files, the
sheet tab names will be used to determine which table in the source dataset the
sheet belongs to. For all other files, the file name will be used to determine
which table the file belongs to.

In order to determine the table name based on the sheet or file name, both the
extension and any text after the first opening square or round bracket are
ignored. After this, the longest matching table name (in the source dataset)
that is found in the file name or sheet name is used. For example, a file named
"1. WWMeasure[2024-12-20].csv" will be a valid file name for the table
"WWMeasure". If no match is found then the file or sheet is ignored.

Alternatively, instead of (or in addition to) specifying an input directory,
one can specify individual input data files. The same mechanism for determining
the table name is used as described above for directories. Additionally, using
files instead of directories allows you to override this table name behavior by
preceding the file path with the table name and a colon. For example,
"WWMeasure:data/table.csv" will load the file at "data/table.csv" and assign it
to the table "WWMeasure".

A full example is shown below:

```console
odm-map \
    --module odm-v1-to-v2 \
    --output-dir "path/to/outputdata" \
    "WWMeasure:path/to/mymeasures1.csv" \
    "WWMeasure:path/to/mymeasures2.csv" \
    "path/to/Sample.csv"
```

In the above example, the input files "path/to/mymeasures1.csv" and
"path/to/mymeasures2.csv" belong to the "WWMeasure" table, and the input file
"/path/to/Sample.csv" belongs to the "Sample" table.

For mapping NWSS Reporting format to ODM v2, simply change the `--module` and
update the input data to point to your NWSS data:

```console
odm-map \
    --module nwss-reporting-to-v2 \
    --output-dir "path/to/outputdata" \
    "path/to/nwss/inputdata"
```

All built-in modules can be found at
[/odm_map/data/modules](/odm_map/data/modules). Alternatively, a list of
installed conversion modules can be seen by running:

```console
odm-map --help
```

If you have created a custom module, use the `--module-path` argument to point
to the full path of the module directory instead of `--module`:

```console
odm-map \
    --module-path "path/to/module" \
    --output-dir "path/to/outputdata" \
    "path/to/inputdata"
```

`--module-path` can also point to a ZIP file containing the module. This is
designed to make it easier to distribute modules in single ZIP files. To create
a ZIP module simply compress the root directory of a module into a ZIP file.

### CLI Arguments

As mentioned above, the general syntax for running the program is:

```console
odm-map [--options] input1 input2 input3 ...
```

The `input` arguments are either directories or files to map.

The following command-line options can be specified with odm-map:

| Parameter            | Description |
|:---------------------|:----------- |
| `--module`           | The conversion module to use. The module specifies the source (eg. NWSS) and target (eg. ODM v2) database formats. Only one of `--module` or `--module-path` must be specified. A list of available modules can be seen by running the script with the `--help` flag. |
| `--module-path`      | The path of the directory of the module to use, or the path to a module stored in a ZIP file to use. This is used for custom modules. Only one of `--module` or `--module-path` must be specified. |
| `--output-dir`       | The directory to save the mapped data to. The file names will be the output table names, and are in CSV format. This command-line parameter is required. |
| `--max-processes`    | Number of processors to use while mapping. For large datasets this can help improve performance. By default only one process is used. |
| `--max-rows`         | *(For debugging purposes)* Maximum number of rows to map from each source table. If not specified, or 0, then all rows are mapped. |
| `--temp-dir`         | *(For debugging purposes)* Optional directory to save temporary data to, which are intermediary files created during the mapping. If left unspecified then a directory in the system temporary directory location is created, and deleted once mapping is complete. This is typically left blank and is mainly used for debugging purposes. |
| `--debug`            | *(For debugging purposes)* Set this flag to run in debug mode. In debug mode there will be additional columns in the final mapped output files. The debug columns include the contents of the ID columns before ID generation was performed, and columns used for tracking such as the source file name and row that the output row was generated from. Rows with duplicate primary keys are also retained rather than the default behavior of being dropped. An additional column will be added where the value is `True` if that row would be dropped if the Mapper was run without debug mode enabled. Depending on the module, some intermediary data tables will also be saved to disk. |

## Performance

Depending on the size of your dataset and the performance of your computer,
mapping can be very time consuming. For example, mapping a NWSS dataset with
650,000 rows to ODM v2 can result in output of over 30,000,000 rows, and can
take 15 hours or more to complete on a high-end computer. Smaller datasets can
be mapped in a matter of minutes. For large datasets, a considerable amount of
RAM or a large RAM disk is required. The most time consuming steps are the
"Initial Mapping" and "Generating IDs" steps.

## Python API

The mapper can also be used programmatically from Python. The main entry point
is the `Pipeline` class in `odm_map.pipeline`:

```python
from odm_map.pipeline import Pipeline

pipeline = Pipeline(
    module="odm-v1-to-v2",  # use a built-in module name
    module_path=None,
)

result = pipeline.run(
    data_files={
        "WWMeasure": ["path/to/wwmeasure.csv"],
        "Sample": ["path/to/sample.csv"],
    },
    output_dir="path/to/output",
)
```

To use a custom module instead of a built-in one, pass `module=None` and set
`module_path` to the directory (or ZIP file) containing the module:

```python
pipeline = Pipeline(
    module=None,
    module_path="path/to/my-module",
)
```

### `Pipeline.run()` Parameters

| Parameter | Type | Default | Description |
|:----------|:-----|:--------|:------------|
| `data_files` | `Dict[str, List[str \| Path]]` | required | Dictionary of source table name → list of file paths to load. For Excel files, use a dict with keys `"file"` and `"sheet"`. |
| `output_dir` | `str` | required | Directory to save output CSV files to. |
| `temp_dir` | `str \| Path` | `None` | Directory for intermediate files. If `None`, a temporary directory is created and deleted when done. Set this for debugging. |
| `max_rows` | `int` | `None` | Maximum rows to load per input file. `None` or `0` loads all rows. |
| `max_processes` | `int` | `1` | Number of parallel processes for the mapping step. |
| `multi_bar_progress` | `bool` | `True` | Show multiple simultaneous progress bars. Set to `False` in Jupyter notebooks. |
| `debug_mode` | `bool` | `False` | If `True`, retains extra tracking columns and duplicate rows in the output, and saves intermediate files to `temp_dir`. |

`pipeline.run()` returns a `Dict[str, List[pd.DataFrame]]` containing the final
mapped DataFrames (keyed by output table name).

## Custom Modules

Mapping modules specify all the rules for mapping from a source database (eg.
NWSS) to a target database (eg. ODM v2). A module consists of a directory
containing various configuration files. Modules for mapping between custom
source and target database formats can be created. For detailed instructions,
please see the [Custom Modules](docs/custom_modules.md) documentation.

## Contributing

To set up a development environment, understand the codebase structure, or
submit a pull request, see [CONTRIBUTING.md](CONTRIBUTING.md).
