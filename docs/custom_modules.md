# Custom Modules

## Introduction

A module is a collection of rules and configuration options, split up into
multiple steps, that define how to map from one database format (eg. NWSS) to a
target database format (eg. ODM v2). The ODM Mapper contains some built-in
modules located at [/odm_map/data/modules](/odm_map/data/modules), but custom
modules can be created to support your own source and target database formats.
A module and all its associated files are stored in a directory. When running
the mapper from the command-line, either a module name (for built-in modules)
or a module directory (for custom modules) can be specified.

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
      log_file: "{output_dir}/change_log_input.xlsx"
      operations:
        - format_and_match_columns: [ lowercase, { remove_chars: "-"}, alpha_numeric_underscore, single_underscores, trim_trailing_underscores ]
        - add_ontology_ids_to_enums:
            match_ontology_id: "\\[[A-Za-z0-9_]+:[A-Za-z0-9_]+\\]$"
        - correct_enums: True
        - check_patterns: True
  - action: save
    if: "{debug_mode}"
    params:
      output_dir: "{temp}/cleaned_data/"
      output_name: "{class_name}[cleaned].csv"
      progress_bar_title: Saving Cleaned Data
  - action: select_enum_hierarchy
    params:
      schema: schemas/nwss_reporting.yaml
      config: enum_hierarchy/config.yaml
  - action: map
    params:
      source_schema: schemas/nwss_reporting.yaml
      target_schema: schemas/odm_v2.yaml
      mappers_dir: mappers
  - action: expand
    params:
      config: expander/expander_config.yaml
  - action: filter
    params:
      filters: filters/nwss_reporting_to_v2_filters.csv
  - action: save
    if: "{debug_mode}"
    params:
      output_dir: "{temp}/mapped_data/"
      output_name: "{class_name}[preid].csv"
  - action: generate_ids
    params:
      schema: "schemas/odm_v2.yaml"
      id_code: ids/nwss_reporting_to_v2_id_code.xlsx
      id_config: ids/nwss_reporting_to_v2_id_config.yaml
  - action: drop_columns
    if: "{not_debug_mode}"
    params:
      drop_tracking_columns: True
      drop_extra_columns: True
      keep_columns_in_schema_only: False
      schema: schemas/odm_v3.yaml
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
available actions, each with its own document, is provided below.

## Actions

Each action has its own document under [docs/actions/](actions/). Every one of
them describes what the action does, where it belongs in a pipeline, all of its
parameters, and how to prepare the configuration files and other files that the
action needs.

| Action | Document | Purpose |
| :----- | :------- | :------ |
| `clean` | [clean.md](actions/clean.md) | Normalize column names, correct enumeration values, and check patterns against a LinkML schema |
| `select_enum_hierarchy` | [select_enum_hierarchy.md](actions/select_enum_hierarchy.md) | For multivalued enum slots, drop values that are ancestors of other values in the same cell |
| `map` | [map.md](actions/map.md) | Transform data from the source format to the target format with LinkML-Map schemas |
| `prepare_wide_to_long` | [prepare_wide_to_long.md](actions/prepare_wide_to_long.md) | Rearrange wide-format data and generate the mappers, schema, and ID code needed to map it to long format |
| `expand` | [expand.md](actions/expand.md) | Turn multivalued (array) cells into one row per array item |
| `filter` | [filter.md](actions/filter.md) | Remove unwanted rows using filtering rules |
| `generate_ids` | [generate_ids.md](actions/generate_ids.md) | Generate primary and foreign keys to link the output tables |
| `drop_columns` | [drop_columns.md](actions/drop_columns.md) | Remove internal tracking, `_extra_`, and non-schema columns |
| `save` | [save.md](actions/save.md) | Write the current data to CSV files |

[Pipeline Actions](actions/README.md) covers what applies to every action: the
structure of a step, the `if` key for conditional steps, the string
interpolation variables, how paths are resolved, and the order actions are
usually combined in. Read it before the individual action documents.

Below is an example step that performs the `save` action:

```yaml
- action: save
  if: "{debug_mode}"
  params:
    output_dir: "{temp}/mapped_data/"
    output_name: "{class_name}[preid].csv"
```

Some values can contain string interpolation variables, such as `{debug_mode}`,
`{not_debug_mode}`, `{temp}`, `{output_dir}`, `{shared}`, and `{class_name}`.
Which variables are available depends on the action and the parameter, and each
action document lists them. `{debug_mode}` is `True` when debug mode is enabled
(with the `--debug` command-line flag) and `False` otherwise, and
`{not_debug_mode}` is its opposite. The `if` key runs a step only when its value
evaluates to true, which is how a step can be limited to debug runs.

`{shared}` and `{temp}` may both be used in the paths of a module's own files,
but only at the very start of the path. For example `"{temp}/mapped_data/"` is
valid, while `"data/{temp}/mapped_data/"` and `"/{temp}/mapped_data/"` are both
invalid. `{temp}` points to a temporary directory (whose contents may be deleted
once the pipeline is complete, unless the temporary directory is set explicitly
with the `--temp-dir` option), and `{shared}` points to the directory of the
shared data module.

## Module Directory Layout

A module is a directory containing `config.yaml` plus the files its steps refer
to. Nothing about the subdirectory names is enforced — the paths in
`config.yaml` are what matter — but the built-in modules use the following
layout, and following it makes a module easier to read:

```text
my-source-to-v3/
├── config.yaml            # The module configuration file (required, this name)
├── schemas/               # LinkML schemas for the source and target formats
├── mappers/               # LinkML-Map YAML files            -> map
├── filters/               # Filter rule CSV/Excel files      -> filter
├── ids/                   # ID code files and ID config YAML -> generate_ids
├── expander/              # Expander config YAML             -> expand
├── enum_hierarchy/        # Enum hierarchy config YAML       -> select_enum_hierarchy
└── wide_to_long/          # Wide-to-long config YAML         -> prepare_wide_to_long
```

Only include the directories your steps actually use. Files shared between
several modules belong in the `_shared` module at
[/odm_map/data/modules/_shared](/odm_map/data/modules/_shared) and are
referenced with the `{shared}` prefix, as the built-in modules do for the ODM
schemas, the general ID code, and the shared required-value filters.

A module can be distributed as a ZIP file of this directory, and run with
`--module-path path/to/module.zip`.

## Related Documentation

| Document | Description |
| :------- | :---------- |
| [Pipeline Actions](actions/README.md) | Concepts common to all actions, plus the index of per-action documents |
| [filters.md](filters.md) | The filter file format and every filter operation, used by the [`filter`](actions/filter.md) action |
| [id_generator.md](id_generator.md) | The ID code and ID config files, used by the [`generate_ids`](actions/generate_ids.md) action |
| [wide_to_long_spec.md](wide_to_long_spec.md) | The wide-format column naming scheme, used by the [`prepare_wide_to_long`](actions/prepare_wide_to_long.md) action |
| [README.md](../README.md) | Installation and command-line usage |
| [CONTRIBUTING.md](../CONTRIBUTING.md) | Developer setup and code structure |
