# Reference

Exact descriptions of the Mapper's interfaces: the command line, the Python API,
and the module configuration file. For task-oriented instructions see the
[How-to guides](../how-to/how_to.md); for the ideas behind these interfaces see
[How the Mapper Works](../explanation/explanation.md).

- [Command-Line Interface](#command-line-interface)
- [Python API](#python-api)
- [Module Configuration](#module-configuration)
- [Module Directory Layout](#module-directory-layout)
- [Further Reference Documents](#further-reference-documents)

## Command-Line Interface

Installing the package provides the `odm-map` command, implemented by
[/odm_map/pipeline_cli.py](https://github.com/PHES-ODM/PHES-ODM-Mapper/blob/main/odm_map/pipeline_cli.py).

```console
odm-map [--options] input1 input2 input3 ...
```

### Inputs

The positional `input` arguments are the files and directories to map, and at
least one is required.

- A **directory** is scanned for files with the extensions `.csv`, `.tsv`,
  `.txt`, and `.xlsx`. Files that cannot be attributed to a source table are
  ignored with a warning.
- A **file** is loaded on its own. A `.csv`, `.tsv`, or `.txt` path may be
  prefixed with a table name and a colon (`WWMeasure:path/to/data.csv`) to state
  which table it belongs to. An explicit prefix must name an existing table
  exactly, including case.
- An **Excel workbook** contributes one table per sheet tab, with the tab name
  determining the table. Sheets matching no table are skipped.

Without an explicit prefix, the table is derived from the file or sheet name:
the extension and everything from the first opening square or round bracket
onward are removed, and the longest source table name occurring in the remainder
is used, matched case-insensitively. `1. WWMeasure[2024-12-20].csv` therefore
loads the `WWMeasure` table.

If no input file matches any table, the run stops and lists the recognized table
names.

### Options

| Option | Description |
|:-------|:----------- |
| `--module` | The built-in conversion module to use. The module specifies the source (eg. NWSS) and target (eg. ODM v3) database formats. Exactly one of `--module` or `--module-path` must be given. Run with `--help` to list the installed modules. |
| `--module-path` | The directory, or ZIP file, of the module to use. This is how custom modules are run. Exactly one of `--module` or `--module-path` must be given. |
| `--output-dir` | The directory to save the mapped data to. One CSV file is written per output table, named after the table. Required. |
| `--max-processes` | Number of processes to use while mapping. For large datasets this can improve performance considerably. A non-positive value uses every available processor. Defaults to `1`, which maps without multiprocessing. |
| `--max-rows` | *(For debugging purposes)* Maximum number of rows to load from each input file. `0`, the default, loads all rows. |
| `--temp-dir` | *(For debugging purposes)* Directory to write intermediate files to. If given, the directory is kept after the run; if omitted, a directory is created in the system temporary location and deleted when the run finishes. |
| `--debug` | *(For debugging purposes)* Run in debug mode. The output keeps the internal tracking columns, the ID columns as they were before ID generation, and rows that would otherwise be dropped for having duplicate primary keys — with an added column that is `True` for each such row. Depending on the module, extra intermediate tables are also written to the temporary directory. |
| `--help` | Show the options and the list of installed modules, then exit. |

## Python API

The entry point is the `Pipeline` class in `odm_map.pipeline`:

```python
from odm_map.pipeline import Pipeline

pipeline = Pipeline(
    module="odm-v1-to-v3",   # a built-in module name
    module_path=None,
)

tables = pipeline.run(
    data_files={
        "WWMeasure": ["path/to/wwmeasure.csv"],
        "Sample": ["path/to/sample.csv"],
    },
    output_dir="path/to/output",
)
```

### `Pipeline()` parameters

| Parameter | Type | Description |
|:----------|:-----|:------------|
| `module` | `str \| PipelineModule \| None` | The name of a built-in module, or an already-loaded `PipelineModule`. Pass `None` to use `module_path` instead. |
| `module_path` | `str \| Path \| None` | The directory or ZIP file of the module to use. Pass `None` when `module` names a built-in module. |

Exactly one of `module` and `module_path` is used; giving a `module` name takes
precedence.

### `Pipeline.run()` parameters

| Parameter | Type | Default | Description |
|:----------|:-----|:--------|:------------|
| `data_files` | `Dict[str, List[str \| Path \| dict]]` | required | Source table name to the list of files holding that table. Unlike the command line, the table is stated directly, so file names do not matter. For a sheet in an Excel workbook, give `{"excel_file": <path>, "sheet": <sheet name>}` in place of a path. |
| `output_dir` | `str` | required | Directory to save the output CSV files to. |
| `temp_dir` | `str \| Path` | `None` | Directory for intermediate files. If `None`, a temporary directory is created and deleted when the run finishes. Set it to keep the intermediate files for inspection. |
| `max_rows` | `int` | `None` | Maximum rows to load per input file. `None` or `0` loads all rows. |
| `max_processes` | `int` | `1` | Number of processes to use for the mapping step. Non-positive uses every available processor. |
| `multi_bar_progress` | `bool` | `True` | Show several simultaneous progress bars. Set to `False` in Jupyter notebooks. |
| `debug_mode` | `bool` | `False` | Equivalent to the `--debug` flag: retains internal columns and duplicate rows in the output, and writes extra intermediate files to `temp_dir`. |

`run()` writes the output CSV files and returns a `Dict[str,
List[pd.DataFrame]]` of the final mapped DataFrames, keyed by output table name.

## Module Configuration

A module is a directory containing a file named `config.yaml` in its root, plus
the files that its steps refer to. `config.yaml` defines the conversion:

```yaml
title: NWSS Reporting to ODM v3

source_schema: schemas/nwss_reporting.yaml

steps:
  - action: clean
    params:
      schema: schemas/nwss_reporting.yaml
      log_file: "{output_dir}/logs/change_log_input.xlsx"
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
      target_schema: schemas/odm_v3.yaml
      mappers_dir: mappers
  - action: expand
    params:
      config: expander/expander_config.yaml
  - action: filter
    params:
      filters: filters/nwss_reporting_to_v3_filters.csv
  - action: save
    if: "{debug_mode}"
    params:
      output_dir: "{temp}/mapped_data/"
      output_name: "{class_name}[preid].csv"
  - action: generate_ids
    params:
      schema: "schemas/odm_v3.yaml"
      id_code: ids/nwss_reporting_to_v3_id_code.xlsx
      id_config: ids/nwss_reporting_to_v3_id_code.yaml
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

### Top-level keys

| Key | Required | Description |
| :-- | :------- | :---------- |
| `title` | Required | A very short description of the mapping the module performs. It is shown in the module list printed by `odm-map --help`. |
| `source_schema` | Required | Module-relative path to the LinkML schema of the source dataset. Its tree root class determines the recognized input table names. |
| `steps` | Required | The ordered list of actions that perform the conversion. |

### Steps

Each entry of `steps` is one step: an `action` name, an optional `if`
condition, and the action's `params`.

```yaml
- action: save
  if: "{debug_mode}"
  params:
    output_dir: "{temp}/mapped_data/"
    output_name: "{class_name}[preid].csv"
```

[Pipeline Actions](actions/README.md) is the reference for what applies to
every step — the structure of a step, conditional steps, the string
interpolation variables such as `{output_dir}`, `{temp}`, `{shared}`, and
`{debug_mode}`, how module-relative and output paths are resolved, and the order
actions are usually combined in. Each action then has its own document
describing its parameters and the files it reads:

| Action | Purpose |
| :----- | :------ |
| [`clean`](actions/clean.md) | Normalize column names, correct enumeration values, and check patterns against a LinkML schema |
| [`select_enum_hierarchy`](actions/select_enum_hierarchy.md) | For multivalued enum slots, drop values that are ancestors of other values in the same cell |
| [`map`](actions/map.md) | Transform data from the source format to the target format with LinkML-Map schemas |
| [`prepare_wide_to_long`](actions/prepare_wide_to_long.md) | Rearrange wide-format data and generate the mappers, schema, and ID code needed to map it to long format |
| [`expand`](actions/expand.md) | Turn multivalued (array) cells into one row per array item |
| [`filter`](actions/filter.md) | Remove unwanted rows using filtering rules |
| [`generate_ids`](actions/generate_ids.md) | Generate primary and foreign keys to link the output tables |
| [`drop_columns`](actions/drop_columns.md) | Remove internal tracking, `_extra_`, and non-schema columns |
| [`save`](actions/save.md) | Write the current data to CSV files |

An unrecognized action name stops the run with an error.

### LinkML schemas

A module needs a LinkML schema for its source format and one for its target
format — mapping NWSS to ODM v3 requires a schema for NWSS and one for ODM v3.
Each schema defines the format's tables and its enumerations, and has a tree
root class whose slots are the table names.

## Module Directory Layout

Nothing about the subdirectory names is enforced — the paths in `config.yaml`
are what matter — but the built-in modules use the following layout, and
following it makes a module easier to read:

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
[/odm_map/data/modules/_shared](https://github.com/PHES-ODM/PHES-ODM-Mapper/tree/main/odm_map/data/modules/_shared)
and are referenced with the `{shared}` prefix, as the built-in modules do for
the ODM schemas, the general ID code, and the shared required-value filters.

A module can be distributed as a ZIP file of this directory and run with
`--module-path path/to/module.zip`.

The built-in modules at [/odm_map/data/modules](https://github.com/PHES-ODM/PHES-ODM-Mapper/tree/main/odm_map/data/modules)
are complete working examples of everything above.

## Further Reference Documents

| Document | Description |
| :------- | :---------- |
| [Pipeline Actions](actions/README.md) | Concepts common to all actions, plus the index of the per-action documents |
| [Filtering](filters.md) | The filter file format and every filter operation, used by the [`filter`](actions/filter.md) action |
| [ID Generator](id_generator.md) | The ID code and ID config files, used by the [`generate_ids`](actions/generate_ids.md) action |
| [Wide-Long Spec](wide_to_long_spec.md) | The wide-format column naming scheme, used by the [`prepare_wide_to_long`](actions/prepare_wide_to_long.md) action |
