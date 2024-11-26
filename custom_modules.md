# Custom Modules

## Important Note

This document is a work in progress.

## Introduction

A module is a collection of rules and configuration options, split up into
multiple steps, that define how to map from one database format (eg. NWSS) to a
target database format (eg. ODM v2). The ODM Mapper contains some built-in
modules located at [data/modules](data/modules), but custom modules can be
created to support your own source and target database formats. A module and
all its associated files are stored in a directory. When running the mapper
from the command-line, either a module name (for built-in modules) or a module
directory (for custom modules) can be specified.

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
      progress_id: Saving Cleaned Data
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
      progress_id: Saving Data
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
variable is always available and is `True` if debug mode is enabled (which can
be specified from the command-line) and is `False` during a normal run where
debug mode is not enabled. The actions, required `params` values, and the
available variables from string interpolation are listed in the following
sections.

### Action: clean

Example:

```yaml
- action: clean
  params:
    schema: schemas/nwss_reporting.yaml
```

| Parameter      | Required/Optional | Description |
| :--------------| :---------------- | :---------- |
| schema         | Required          |             |

### Action: generate_ids

Example:

```yaml
- action: generate_ids
  params:
    id_code: ids/nwss_reporting_to_v2_id_code.xlsx
    id_config: ids/nwss_reporting_to_v2_id_config.yaml
```

| Parameter      | Required/Optional | Description |
| :--------------| :---------------- | :---------- |
| id_code        | Required          |             |
| id_code_sheet  | Optional          |             |
| id_config      | Required          |             |

### Action: map

Example:

```yaml
- action: map
  params:
    source_schema: schemas/nwss_reporting.yaml
    target_schema: schemas/odm_v2.yaml
    mapper_dir: mappers
```

| Parameter      | Required/Optional | Description |
| :--------------| :---------------- | :---------- |
| source_schema  | Required          |             |
| target_schema  | Required          |             |
| mappers_dir    | Required          |             |
| prepare_barid  | Optional          |             |
| map_barid      | Optional          |             |

### Action: filter

Example:

```yaml
- action: filter
  params:
    filters: filters/nwss_reporting_to_v2_filters.csv
```

| Parameter      | Required/Optional | Description |
| :--------------| :---------------- | :---------- |
| filters        | Required          |             |

### Action: save

Example:

```yaml
- action: save
  if: "{debug_mode}"
  params:
    output_dir: "{temp_dir}/cleaned_data/"
    output_name: "{class_name}[cleaned].csv"
    progress_id: Saving Cleaned Data
```

| Parameter      | Required/Optional | Description |
| :--------------| :---------------- | :---------- |
| output_dir     | Required          |             |
| output_name    | Required          |             |
| progress_id    | Optional          | Can be empty |

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

## Pre-ID Filters

After LinkML-Map is run using all the YAML mappers, but before the ID generator
is run (see below), all output tables/classes can be optionally filtered to
remove various rows. For example, rows where the `value` column is blank, or
where the `measure` column is equal to `<ignore>`, can be removed. For details
on how to configure the filters, see [Filtering Data](filters.md).

## ID Generator

After mapping is performed by LinkML-Map and the output is optionally filtered,
various IDs in the output can be generated based on the ID code generation
config file, which is an Excel or CSV file. For example, we may want to
generate a `measureRepID` value if one was not available in the mapped data. An
example formula might be to concatenate the `sampleID` and the value found in
the `measure` column (eg. `sample001CovN1`). When configured properly, these
IDs can be linked between various output tables. For details on how to create
the ID code, see [ID Generator](id_generator.md).
