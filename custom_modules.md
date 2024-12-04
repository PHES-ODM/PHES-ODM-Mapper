# Custom Modules

## Important Note

This document is a work in progress.

## Introduction

A module is a collection of rules and configuration options, split up into
multiple steps, that define how to map from one database format (eg. NWSS) to a
target database format (eg. ODM v2). The ODM Mapper contains some built-in
modules located at [/odm_map/data/modules](/odm_map/data/modules), but
custom modules can be created to support your own source and target database
formats. A module and all its associated files are stored in a directory. When
running the mapper from the command-line, either a module name (for built-in
modules) or a module directory (for custom modules) can be specified.

This document, including its sub-documents, describe how to create your own
module.

## LinkML Schemas

At a minimum a LinkML schema for the source and target databases are required.
For example, mapping NWSS to ODM v2 requires a LinkML schema for NWSS and for
ODM v2. The schemas should define all the tables for each database, as well as
enumerations. In each schema, there should be a tree root class, where all the
tree root's slots are the names of the database tables.

## Module Configuration

The module configuration file should be located in the root directory of the
module and named `config.yaml`. It defines the steps and the locations of all
necessary files needed for mapping, filtering, and ID generation. An example
configuration is shown below:

```yaml
title: NWSS Reporting to ODM v2

source_schema: schemas/nwss_reporting.yaml

steps:
  - action: clean
    params:
      schema: schemas/nwss_reporting.yaml
  - action: save
    if: "{debug_mode}"
    params:
      output_dir: "{temp_dir}/cleaned_data/"
      output_name: "{class_name}[cleaned].csv"
      progress_bar_title: Saving Cleaned Data
  - action: map
    params:
      source_schema: schemas/nwss_reporting.yaml
      target_schema: schemas/odm_v2.yaml
      mapper_dir: mappers
  - action: filter
    params:
      filters: filters/nwss_reporting_to_v2_filters.csv
  - action: save
    if: "{debug_mode}"
    params:
      output_dir: "{temp_dir}/mapped_data/"
      output_name: "{class_name}[preid].csv"
  - action: generate_ids
    params:
      id_code: ids/nwss_reporting_to_v2_id_code.xlsx
      id_config: ids/nwss_reporting_to_v2_id_config.yaml
  - action: save
    params:
      output_dir: "{output_dir}"
      output_name: "{class_name}.csv"
      progress_bar_title: Saving Data
```

The `title` is a required field that consists of a very short description of
the mapping performed by the module. `source_schema` is the LinkML schema of
the source dataset. In the above example, this is the NWSS Reporting format.
The `steps` field specifies the steps of actions performed to do a full
mapping. There are various kinds of actions that can be performed, such as
cleaning the data (by correcting capitalization of enumeration values, checking
for missing columns, etc), mapping using LinkML map schemas, filtering data to
removed unwanted rows, generating IDs and linking the tables with
primary/foreign keys, and saving the data to disk. Each action takes a
dictionary of parameters in the action's `params` field. A full list of
available actions are provided below.

## Actions

Below is an example step that performs the `save` action:

```yaml
- action: save
  if: "{debug_mode}"
  params:
    output_dir: "{temp_dir}/mapped_data/"
    output_name: "{class_name}[preid].csv"
```

In some of the values above, string interpolation variables can be specified,
such as `{debug_mode}`, `{temp_dir}`, and `{class_name}`. Which variables are
available in the `params` field depends on the action. The `debug_mode`
variable is `True` if debug mode is enabled (which can be specified from the
command-line) and is `False` during a normal run where debug mode is not
enabled. The actions, required `params` values, and the available variables
from string interpolation are listed in the following sections.

### Action: clean

Example:

```yaml
- action: clean
  params:
    schema: schemas/nwss_reporting.yaml
```

| Parameter      | Required/Optional | Description |
| :--------------| :---------------- | :---------- |
| schema         | Required          | The path to the LinkML schema that the cleaning is based on. This path is relative to the root directory of the module. |

Clean the data using the specified LinkML schema. The schema should be for the
current format that the data is in (eg. NWSS, PHA4GE, ODM v1, ODM v2, etc).
Cleaning will correct capitalization of enumeration values, report unknown
enumeration values (while leaving them unchanged), report missing columns, and
report additional unrecognized columns. Missing columns will typically be
treated as blank, while unrecognized columns will typically be ignored.

### Action: generate_ids

Example:

```yaml
- action: generate_ids
  params:
    id_code: ids/nwss_reporting_to_v2_id_code.xlsx
    id_code_sheet: id_code
    id_config: ids/nwss_reporting_to_v2_id_config.yaml
```

| Parameter      | Required/Optional | Description |
| :--------------| :---------------- | :---------- |
| id_code        | Required          | The path to the file containing all the ID generation rules/code. This can be an Excel spreadsheet or a CSV file. If it is an Excel spreadsheet that has more than one sheet/tab, then the sheet to use within the spreadsheet can be specified by `id_code_sheet`. |
| id_code_sheet  | Optional          | If `id_code` is an Excel file, then `id_code_sheet` can optionally be specified to indicate which sheet within the spreadsheet should be used. If `id_code_sheet` is empty then the first sheet within the Excel file is used. |
| id_config      | Required          | The configuration file for ID code generation. This config file specifies configurations such as the primary key for each of the input tables. |

Generate all the IDs within the DataFrame tables, using the specified
configuration and rules. Primary and foreign keys will be created, allowing
linking between the various tables of the dataset. See the [ID Generator
document](id_generator.md) for details on how to create the ID generation code
and config files.

The `map` action is usually performed at an earlier step before the
`generate_ids` action.

Along with the `map` action, this is the most time-consuming action, and can
take half a day or more to complete for exceptionally large datasets. Smaller
datasets can be processed within a matter of minutes.

### Action: map

Example:

```yaml
- action: map
  params:
    source_schema: schemas/nwss_reporting.yaml
    target_schema: schemas/odm_v2.yaml
    mapper_dir: mappers
```

| Parameter          | Required/Optional | Description |
| :----------------- | :---------------- | :---------- |
| source_schema      | Required          | The LinkML schema for the source dataset, that we are mapping from. This is a path relative to the root directory of the module. |
| target_schema      | Required          | The LinkML schema for the target dataset, that we are mapping to. This is a path relative to the root directory of the module. |
| mappers_dir        | Required          | The directory containing all the LinkML-Map schemas that specify how to perform the mapping. This is a path relative to the root directory of the module. See the [LinkML-Map Mappers](#linkml-map-mappers) section below for additional information on the map schemas found in the `mappers_dir` directory. |
| prepare_bar_title  | Optional          | The title to use for the progress bar displayed when preparing the data before the mapping occurs (eg. "Preparing Data"). If not specified a default string is used. |
| map_bar_title      | Optional          | The title to use for the progress bar displayed when doing the actual mapping (eg. "Mapping Data"). If not specified a default string is used. |

The `map` action performs the actual mapping, transforming the data from a
source dataset to a target dataset. A LinkML schema for both the source and
target datasets is required, along with a directory containing all the required
LinkML-Map schemas to perform the mapping. Once this step is complete all data
will be in the format of the target dataset, which should be taken into account
for any subsequent steps. See the [LinkML-Map Mappers](#linkml-map-mappers)
section below for additional information on the map schemas found in the
`mappers_dir` directory.

The `generate_ids` action is usually performed at a later step after the `map`
action.

Along with the `generate_ids` action, this is the most time-consuming action,
and can take half a day or more to complete for exceptionally large datasets.
Smaller datasets can be processed within a matter of minutes.

### Action: filter

Example:

```yaml
- action: filter
  params:
    filters: filters/nwss_reporting_to_v2_filters.csv
```

| Parameter      | Required/Optional | Description |
| :--------------| :---------------- | :---------- |
| filters        | Required          | A CSV or Excel file specifying all the filtering rules. If an Excel file then the first sheet is used. See [Filtering Data](filters.md) for instructions on how to create the filtering configuration file. |

The `filter` action allows the removal of rows in the data that are not
desired. For example, rows with a missing but required `value` field, or rows
where a value of `<ignore>` are found. These filtering rules are usually (but
not always) applied after the `map`.

See [Filtering Data](filters.md) for instructions on how to create the
filtering configuration file.

### Action: save

Example:

```yaml
- action: save
  if: "{debug_mode}"
  params:
    output_dir: "{output_dir}/cleaned_data/"
    output_name: "{class_name}[cleaned].csv"
    progress_bar_title: Saving Cleaned Data
```

| Parameter          | Required/Optional | Description |
| :----------------- | :---------------- | :---------- |
| output_dir         | Required          | The directory to save the output to. Can include the `{output_dir}` (output directory, usually specified on the command-line), `{temp_dir}` (temporary directory, either specified on the command line or optionally within the system's temporary directory), and `{debug_mode}` string interpolation values. |
| output_name        | Required          | The name to give each file that is saved within the output directory. These names can include all the string interpolation variables for `output_dir`, plus the additional value `{class_name}`, which is the class or table name that the data represents. |
| progress_bar_title | Optional          | The title to give the progress bar when saving the data to disk. If empty then no progress bar is shown. |

Save all DataFrames to disk, in the directory specified by `output_dir` using
the file names specified with `output_name`. `output_dir` can include the
`{temp_dir}`, `{output_dir}`, and `{debug_mode}` string interpolation
variables. `output_name` can include these variables plus the `{class_name}`
variable, which indicates the class or table name that the DataFrame
represents.

Usually the `save` action is performed as the last action in the series of
steps specified in the module configuration file. Sometimes, however, for
debugging purposes the `save` action is used in between earlier steps so that
the contents of the DataFrames can be viewed to ensure they are correct. If you
would like to only perform a specific `save` action while in debug mode (which
can be specified as a flag from the command-line), you can use "{debug_mode}"
in the `if` key of the step. To always perform the `save` action, whether in
debug mode or not, remove the `if` key in the step.

## LinkML-Map Mappers

The mappers directory contains all mapping schemas that define the mappings.
These should all be valid [LinkML-Map](https://github.com/linkml/linkml-map)
YAML files. All YAML files in this directory are used, with the mapping outputs
resulting from each YAML file concatenated together for all the different
target tables/classes.

A few rules should be followed:

1. In the `class_derivations` section of each mapper file, the output table
   (ie. the top-level keys within `class_derivations`) should be the name of a
   class found within the target database. Following the class name, additional
   optional text can be included in square brackets (this text is ignored, eg.
   `measures[001]` will be for the target class `measures`).
2. There should be a class derivation for the tree root class. The slot
   derivations for this class should be for all the target class names found in
   the mapper file (eg. `measures[001]` from the previous example).

The following is an example mapper file that populates the `measures` table in
ODM v2 from the `WWMeasure` table in ODM v1 (with `Container` being the tree
root of the target database):

```yaml
class_derivations:
  measures[001]:
    name: measures[001]
    populated_from: WWMeasure
    slot_derivations:
      organizationID:
        name: organizationID
        populated_from: labID
      # ...
  Container:
    name: Container
    slot_derivations:
      measures[001]:
        populated_from: WWMeasure
```

## Filters

All tables/classes can be optionally filtered to remove various rows. For
example, rows where the `value` column is blank, or where the `measure` column
is equal to `<ignore>`, can be removed. For details on how to configure the
filters, see [Filtering Data](filters.md).

## ID Generator

Various IDs in the data can be generated based on the ID code generation file,
which is an Excel or CSV file. For example, we may want to generate a
`measureRepID` value if one was not available in the mapped data. An example
formula might be to concatenate the `sampleID` and the value found in the
`measure` column (eg. `sample001CovN1`). When configured properly, these IDs
can be linked between various output tables. For details on how to create the
ID code, see [ID Generator](id_generator.md).
