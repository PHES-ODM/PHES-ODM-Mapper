# <img src="img/ODM-logo.png" align="right" alt="" width="180"/> PHES-ODM Mapper

## Introduction

This repository provides all tools required for mapping between various wastewater reporting database formats and the [Public Health Environmental Surveillance Open Data Model (PHES-ODM)](https://phes-odm.org). Currently supported are conversion from NWSS Reporting to ODM v2 and ODM v1 to ODM v2. More database formats will be provided as needed, and custom conversions can be created. To add support for other databases, see [Custom Modules](#custom-modules) below. If you require help in creating custom modules, contact [mwellman@ohri.ca](mailto:mwellman@orhi.ca).

## Installation

To clone the repository and create a new virtual environment, run the following on the command-line:

```console
git clone git@github.com:Big-Life-Lab/PHES-ODM-Mapper.git
cd PHES-ODM-Mapper
python3 -m venv .env
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
pip3 install -r requirements.txt
```

## Sample Data

Sample ODM v1 data is available if you require a sample dataset to run the mapper on before you have your own data ready, or for testing purposes. The data is provided by the [Ottawa Wastewater Surveillance Consortium on Github](https://github.com/OntarioWastewaterSurveillanceConsortium/sars-cov-2-data). Data can be downloaded manually on Github, or from the command-line using the following:

```console
git clone git@github.com:OntarioWastewaterSurveillanceConsortium/sars-cov-2-data.git
```

Sample data from various locations can be found in the `CSV` directory. Record the location of one of these directories and use it as the `--input_data_dir` parameter below (eg. "sars-cov-2-data/CSV/Ottawa").

## Command-Line Interface

A full mapping can be performed by using the command-line interface (CLI) provided by the script [src/map_cli.py](src/map_cli.py). Be sure to always activate the virtual environment as described in the [Installation](#installation) section above before running the script.

Below is an example to map ODM v1 data (found in "path/to/inputdata") to ODM v2 data (and save the mapped data to "path/to/outputdata"):

```console
python3 src/map_cli.py \
    --module odm_v1_to_v2 \
    --input_data_dir "path/to/inputdata" \
    --output_dir "path/to/outputdata"
```

In the above example, all data files (csv, txt, tsv, yaml/yml files) in "path/to/inputdata" will be mapped. It will be assumed that the file name (excluding anything after the first opening square or round bracket) is the table name that the data is for (eg. "WWMeasure[2024-09-25].csv" will be assumed to be for the "WWMeasure" table).

Alternatively, instead of specifying an input directory, one can use the `--input_data_files` command-line argument to specify input data files while explicitly specifying the table name for the files:

```console
python3 src/map_cli.py \
    --module odm_v1_to_v2 \
    --input_data_files WWMeasure "path/to/WWMeasure1.csv" WWMeasure "path/to/WWMeasure2.csv" Sample "path/to/Sample.csv" \
    --output_dir "path/to/outputdata"
```

For mapping NWSS Reporting format to ODM v2, simply change the `module`:

```console
python3 src/map_cli.py \
    --module nwss_reporting_to_v2 \
    --input_data_dir "path/to/inputdata" \
    --output_dir "path/to/outputdata"
```

All built-in modules can be found at [/data/modules](/data/modules), simply use the directory name of the module for the `--module` parameter.

If you have created a custom module, use the `module_dir` argument instead of `module`:

```console
python3 src/map_cli.py \
    --module_dir "path/to/module" \
    --input_data_dir "path/to/inputdata" \
    --input_data_files table1 table1.csv table2 table2.csv \
    --output_dir "path/to/outputdata"
```

### Performance

Depending on the size of your dataset and the performance of your computer, mapping can be very time consuming. For example, mapping a NWSS dataset with 650,000 rows to ODM v2 can result in output of over 30,000,000 rows, and can take 15 hours or more to complete on a high-end computer. Smaller datasets can be mapped in a matter of minutes. The most time consuming steps are the "Initial Mapping" and "Generating IDs" steps.

### CLI Arguments

The following command-line parameters can be specified with map_cli.py:

| Parameter          | Description |
|:-------------------|:----------- |
| `--module`           | The conversion module to use. The module specifies the source (eg. NWSS) and target (eg. ODM v2) database formats. Only one of `module` or `module_dir` must be specified. Current supported values are 'odm_v1_to_v2' and 'nwss_reporting_to_v2'. |
| `--module_dir`       | The directory to the module to use. This is often used for custom modules. Only one of 'module' or 'module_dir' must be specified. |
| `--input_data_dir`   | The directory where the data in the source database format is located. These should be .csv, .tsv, or .txt files (.tsv and .txt are tab-separated files). The file names (without extension) should be the name of the table that the file is for. Additional text can be provided at the end of the file name in square or round brackets, anything after the first opening bracket is ignored (eg. The file "Instrument[2024-09-11].csv" contains data for the "Instrument" table). This command-line parameter is optional and can be combined with `--input_data_files` (at least one of `input_data_dir` and `input_data_files` must be specified). |
| `--input_data_files` | List of space-separated strings specifying the source database table names and the input data files for the tables, which are the data files to map. The list of strings are in pairs, with the first item in each pair is the table name and the second is the filename for the table. If the table name or file name have spaces then they must be enclosed in quotes. For example, `--input_data_files WWMeasure "path/to/WWMeasure data.csv" WWMeasure "path/to/WWMeasure2.csv" Sample "path/to/sample.csv"` will map two files corresponding to the `WWMeasure` table and one file corresponding to the `Sample` table. This command-line parameter is optional and can be combined with `--input_data_dir` (at least one of `input_data_dir` and `input_data_files` must be specified). |
| `--output_dir`       | The directory to save the mapped data to. The file names will be the output table names, and are in CSV format. This command-line parameter is required. |
| `--max_processes`    | Number of processors to use while mapping. For large datasets this can help improve performance. By default only one process is used. |
| `--input_max_rows`   | *(For debugging purposes)* Maximum number of rows to map from each source table. If not specified, or 0, then all rows are mapped. |
| `--temp_dir`         | *(For debugging purposes)* Optional directory to save temporary data to, which are intermediary files created during the mapping. If left unspecified then a directory in the system temporary directory location is created, and deleted once mapping is complete. This is typically left blank and is mainly used for debugging purposes. |
| `--id_debug`         | *(For debugging purposes)* Set this flag to include debug columns in the final mapped output files. The debug columns include the contents of the ID columns before ID generation was performed, and columns used for tracking such as the source file name and row that the output row was generated from. Rows with duplicate primary keys are also retained rather than the default behavior of being have been dropped if `id_debug` was not set. |

## Custom Modules

Mapping modules specify all the rules for mapping from a source database (eg. NWSS) to a target database (eg. ODM v2). A module consists of a directory containing various configuration files. Modules for mapping between custom source and target database formats can be created. For detailed instructions, please see the [Custom Modules](custom_modules.md) documentation.
