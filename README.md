# <img src="img/ODM-logo.png" align="right" alt="" width="180"/> PHES-ODM Mapper

## Introduction

This repository provides all tools required for mapping between various
wastewater reporting database formats and the [Public Health Environmental
Surveillance Open Data Model (PHES-ODM)](https://phes-odm.org). Currently
supported are conversion from NWSS Reporting to ODM v2 and ODM v1 to ODM v2.
More database formats will be provided as needed, and custom conversions can be
created. To add support for other databases, see [Custom
Modules](#custom-modules) below. If you require help in creating custom
modules, contact [mwellman@ohri.ca](mailto:mwellman@orhi.ca).

## Installation

```console
pip install git+https://github.com/Big-Life-Lab/PHES-ODM-Mapper.git
```

## Installation (For Development)

Skip this section if you will not be developing for the PHES-ODM-Mapper library
(but be sure to follow the instructions in the above
[Installation](#installation) section.

To clone the repository, run the following on the command-line:

```console
git clone git@github.com:Big-Life-Lab/PHES-ODM-Mapper.git
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

Install Python library requirements:

```console
pip install -r requirements.txt
```

If you previously installed the package, then uninstall it:

```console
pip uninstall odm_map
```

Install the odm-map package:

```console
pip install -e .
```

## Sample Data

Sample ODM v1 data is available if you require a sample dataset to run the
mapper on before you have your own data ready, or for testing purposes. The
data is provided by the [Ottawa Wastewater Surveillance Consortium on
[Github](https://github.com/OntarioWastewaterSurveillanceConsortium/sars-cov-2-data).
Data can be downloaded manually on Github, or from the command-line using the
following:

```console
git clone git@github.com:OntarioWastewaterSurveillanceConsortium/sars-cov-2-data.git
```

Sample data from various locations can be found in the `CSV` directory. Record
the location of one of these directories and use it as the `--input-dir`
parameter below (eg. "sars-cov-2-data/CSV/Ottawa").

## Command-Line Interface

A full mapping can be performed by using the command-line interface (CLI)
provided by the script
[src/odm_map/pipeline_cli.py](src/odm_map/pipeline_cli.py). Be sure to always
activate the virtual environment as described in the
[Installation](#installation) section above before running the script.

Below is an example to map ODM v1 data (found in "path/to/inputdata") to ODM v2
data (and save the mapped data to "path/to/outputdata"):

```console
odm-map \
    --module odm-v1-to-v2 \
    --input-dir "path/to/inputdata" \
    --output-dir "path/to/outputdata"
```

In the above example, all valid data files (csv, txt, tsv, yaml/yml, xlsx) in
"path/to/inputdata" will be mapped. For Excel files, the sheet tab names will
be used to determine which table in the source dataset the sheet belongs to.
For all other files, the file name will be used to determine which table the
file belongs to.

In order to determine the table name based on the sheet or file name, both the
extension and any text after the first opening square or round bracket are
ignored. After this, the longest matching table name (in the source schema)
that is found in the file name or sheet name is used. For example, a file named
"1. WWMeasure[2024-12-20].csv" will be a valid file name for the table
"WWMeasure". If no match is found then the file or sheet is ignored.

Alternatively, instead of (or in addition to) specifying an input directory,
one can use the `--input-file` command-line argument to specify individual
input data files. The same mechanism for determining the table name is used as
described above for `--input-dir`. Additionally, using `--input-file` allows
you to override this table name behavior by preceding the file path with the
table name and a colon. For example, "WWMeasure:data/table.csv" will load the
file at "data/table.csv" and assign it to the table "WWMeasure".

A full example is shown below (notice that the flag `--input-file` is specified
once for each file):

```console
odm-map \
    --module odm-v1-to-v2 \
    --input-file "WWMeasure:path/to/mymeasures1.csv" \
    --input-file "WWMeasure:path/to/mymeasures2.csv"
    --input-file "path/to/Sample.csv" \
    --output-dir "path/to/outputdata"
```

For mapping NWSS Reporting format to ODM v2, simply change the `module`:

```console
odm-map \
    --module nwss-reporting-to-v2 \
    --input-dir "path/to/inputdata" \
    --output-dir "path/to/outputdata"
```

All built-in modules can be found at [/data/modules](/data/modules), simply use
the directory name of the module for the `--module` parameter.

If you have created a custom module, use the `module_dir` argument instead of
`module`:

```console
odm-map \
    --module-dir "path/to/module" \
    --input-dir "path/to/inputdata" \
    --input-file table1:table1.csv table2:table2.csv \
    --output-dir "path/to/outputdata"
```

### CLI Arguments

The following command-line parameters can be specified with odm-map:

| Parameter            | Description |
|:---------------------|:----------- |
| `--module`           | The conversion module to use. The module specifies the source (eg. NWSS) and target (eg. ODM v2) database formats. Only one of `module` or `module_dir` must be specified. A list of available modules can be seen by running the script with the `--help` flag. |
| `--module-dir`       | The directory to the module to use. This is often used for custom modules. Only one of 'module' or 'module_dir' must be specified. |
| `--input-dir`        | The directory where the data in the source database format is located. These should be .xlsx, .csv, .tsv, or .txt files (.tsv and .txt are tab-separated files). This command-line parameter is optional and can be combined with `--input-file` (at least one of `input-dir` and `input-file` must be specified). |
| `--input-file`       | An individual data file to map. This command-line parameter is optional and can be combined with `--input-dir` (at least one of `input-dir` and `input-file` must be specified). |
| `--output-dir`       | The directory to save the mapped data to. The file names will be the output table names, and are in CSV format. This command-line parameter is required. |
| `--max-processes`    | Number of processors to use while mapping. For large datasets this can help improve performance. By default only one process is used. |
| `--max-rows`         | *(For debugging purposes)* Maximum number of rows to map from each source table. If not specified, or 0, then all rows are mapped. |
| `--temp-dir`         | *(For debugging purposes)* Optional directory to save temporary data to, which are intermediary files created during the mapping. If left unspecified then a directory in the system temporary directory location is created, and deleted once mapping is complete. This is typically left blank and is mainly used for debugging purposes. |
| `--debug`            | *(For debugging purposes)* Set this flag to include debug columns in the final mapped output files. The debug columns include the contents of the ID columns before ID generation was performed, and columns used for tracking such as the source file name and row that the output row was generated from. Rows with duplicate primary keys are also retained rather than the default behavior of being dropped. |

## Performance

Depending on the size of your dataset and the performance of your computer,
mapping can be very time consuming. For example, mapping a NWSS dataset with
650,000 rows to ODM v2 can result in output of over 30,000,000 rows, and can
take 15 hours or more to complete on a high-end computer. Smaller datasets can
be mapped in a matter of minutes. For large datasets, a considerable amount of
RAM or scratch disk is required. The most time consuming steps are the "Initial
Mapping" and "Generating IDs" steps.

## Custom Modules

Mapping modules specify all the rules for mapping from a source database (eg.
NWSS) to a target database (eg. ODM v2). A module consists of a directory
containing various configuration files. Modules for mapping between custom
source and target database formats can be created. For detailed instructions,
please see the [Custom Modules](custom_modules.md) documentation.
