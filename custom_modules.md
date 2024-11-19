# Custom Modules

## Introduction

A module is a collection of rules and configuration options that define how to map from one database format (eg. NWSS) to a target database format (eg. ODM v2). The ODM Mapper contains some built-in modules located at [data/modules](data/modules), but custom modules can be created to support your own source and target database formats. The LinkML-Map YAML files found in the built-in modules were generated with [PHES-ODM-MapGenerator](https://github.com/Big-Life-Lab/PHES-ODM-MapGenerator). A module and all its associated files are stored in a directory, with the directory location specified when running the mapper from the command-line.

The following is a list of components of a module, which are described in this and related documents:

1. *[Module Configuration](#module-configuration)*: The general configuration of the module, primarily specifying where within the module directory that the various required files are located. This is a simple YAML file.
2. *[Source and Target Schemas](#source-and-target-schemas)*: The LinkML schemas representing the source and target databases.
3. *[LinkML-Map Mappers](#linkml-map-mappers)*: The LinkML-Map schemas that define how to map from the source to target databases.
4. *[Pre-ID Filters](#pre-id-filters)*: Optional rules to filter the mapped data after the LinkML Mappers are run but before ID generation, for example to remove unwanted rows or rows with missing information.
5. *[ID Generator](#id-generator)*: Optional rules for generating IDs within the mapped and filtered data. ID generation is fairly flexible and can also allow linking between output database tables (eg. creating primary and foreign keys). It can also generate non-ID fields, such as properly formatting dates and times.

This document, including its sub-documents, describes how to create your own module.

## Module Configuration

The module configuration file should be located in the root directory of the module and named `config.yaml`. It defines the locations of all necessary files needed for mapping, filtering, and ID generation. An example configuration is shown below:

```yaml
title: NWSS Reporting to ODM v2

source_schema: schemas/nwss_reporting.yaml
target_schema: schemas/odm_v2.yaml
mappers: mappers
pre_id_filters: pre_id_filters/nwss_reporting_to_v2_filters.csv
id_code: ids/nwss_reporting_to_v2_id_code.xlsx
id_code_sheet: id_code
id_config: ids/nwss_reporting_to_v2_id_config.yaml
```

Some of these fields can be left blank. See below for a description of all fields:

| Field          | Required | Description |
| :------------- | :------- | :---------- |
| title          | Yes      | A descriptive title to give to the module. |
| source_schema  | Yes      | Location of the LinkML schema for the source database (eg. NWSS) (see [Source and Target Schemas](#source-and-target-schemas) below). |
| target_schema  | Yes      | Location of the LinkML schema for the target database (eg. ODM v2). (see [Source and Target Schemas](#source-and-target-schemas) below). |
| mappers        | Yes      | Directory containing all the LinkML-Map schemas to perform the mapping (see [LinkML-Map Mappers](#linkml-map-mappers) below). |
| pre_id_filters | No       | Filter configuration file specifying how to filter the data after mapping is performed, but before the ID generation step (See [Pre-ID Filters](#pre-id-filters) below). |
| id_code        | No       | Configuration/code for generating IDs after the initial mapping and filtering is performed (See [ID Generator](#id-generator) below). |
| id_code_sheet  | No       | If `id_code` is an Excel file, then this is the name of the sheet to use. If missing or `None` then the first sheet is used. (See [ID Generator](#id-generator) below). |
| id_config      | No       | Additional configuration file for ID generation (See [ID Generator](#id-generator) below). |

## Source and Target Schemas

These are LinkML schemas for both the source and target databases. They should define all the tables for each database, as well as enumerations.

There should be a tree root class, where all the class's slots are the names of the database tables.

## LinkML-Map Mappers

The mappers directory contains all mapping schemas that define the mappings. These should all be valid [LinkML-Map](https://github.com/linkml/linkml-map) YAML files. All YAML files in this directory are used, with the mapping outputs resulting from each YAML file concatenated together for all the different target tables/classes.

A few rules should be followed:

1. In the `class_derivations` section of each mapper file, the output table (ie. the top-level keys within `class_derivations`) should be the name of a class found within the target database. Following the class name, additional optional text can be included in square brackets (this text is ignored, eg. `measures[001]` will be for the target class `measures`).
2. There should be a class derivation for the tree root class. The slot derivations for this class should be for all the target class names found in the mapper file (eg. `measures[001]` from the previous example).

The following is an example mapper file that populates the `measures` table in ODM v2 from the `WWMeasure` table in ODM v1 (with `Container` being the tree root of the target database):

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

After LinkML-Map is run using all the YAML mappers, but before the ID generator is run (see below), all output tables/classes can be optionally filtered to remove various rows. For example, rows where the `value` column is blank, or where the `measure` column is equal to `<ignore>`, can be removed. For details on how to configure the filters, see [Filtering Data](filters.md).

## ID Generator

After mapping is performed by LinkML-Map and the output is optionally filtered, various IDs in the output can be generated based on the ID code generation config file, which is an Excel or CSV file. For example, we may want to generate a `measureRepID` value if one was not available in the mapped data. An example formula might be to concatenate the `sampleID` and the value found in the `measure` column (eg. `sample001CovN1`). When configured properly, these IDs can be linked between various output tables. For details on how to create the ID code, see [ID Generator](id_generator.md).
