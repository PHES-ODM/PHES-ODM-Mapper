# Pipeline Actions

## Introduction

A conversion module performs a mapping as an ordered list of **steps**. Each
step runs one **action**, such as cleaning the input data, mapping it with
LinkML-Map, filtering out unwanted rows, generating IDs, or saving the result to
disk. The steps are defined under the `steps` key of the module configuration
file `config.yaml` (see [Reference](../reference.md#module-configuration)
for the module configuration file as a whole).

Each action has its own document, listed in the table below. Every document
describes what the action does, where it belongs in a pipeline, its parameters,
and how to prepare the configuration files and any other files that the action
needs.

| Action | Document | Purpose |
| :----- | :------- | :------ |
| `clean` | [clean.md](clean.md) | Normalize column names, correct enumeration values, and check patterns against a LinkML schema |
| `select_enum_hierarchy` | [select_enum_hierarchy.md](select_enum_hierarchy.md) | For multivalued enum slots, drop values that are ancestors of other values in the same cell |
| `map` | [map.md](map.md) | Transform data from the source format to the target format with LinkML-Map schemas |
| `prepare_wide_to_long` | [prepare_wide_to_long.md](prepare_wide_to_long.md) | Rearrange wide-format data and generate the mappers, schema, and ID code needed to map it to long format |
| `expand` | [expand.md](expand.md) | Turn multivalued (array) cells into one row per array item |
| `filter` | [filter.md](filter.md) | Remove unwanted rows using filtering rules |
| `generate_ids` | [generate_ids.md](generate_ids.md) | Generate primary and foreign keys to link the output tables |
| `drop_columns` | [drop_columns.md](drop_columns.md) | Remove internal tracking, `_extra_`, and non-schema columns |
| `save` | [save.md](save.md) | Write the current data to CSV files |

## Anatomy of a Step

A step is a dictionary with the keys `action`, an optional `if`, and `params`:

```yaml
- action: save
  if: "{debug_mode}"
  params:
    output_dir: "{temp}/mapped_data/"
    output_name: "{class_name}[preid].csv"
    progress_bar_title: Saving Data
```

| Key | Required/Optional | Description |
| :-- | :---------------- | :---------- |
| `action` | Required | The name of the action to perform. It must be one of the action names in the table above; an unrecognized name stops the run with an error. |
| `if` | Optional | If present, the step only runs when this value evaluates to true. Defaults to running the step. See [Conditional Steps](#conditional-steps) below. |
| `params` | Required (for most actions) | The parameters for the action. Which parameters are available, and which are required, depends on the action. |

The same action can appear any number of times in `steps`. For example, most
built-in modules run `clean` both before mapping (against the source schema) and
after mapping (against the target schema), and run `save` several times so that
intermediate data can be inspected in debug mode.

## Data Flow Between Steps

Every action receives the data as a dictionary where the keys are class (table)
names and the values are lists of DataFrames belonging to that class, and it
returns the same structure. The output of one step is the input to the next.

Two consequences are worth remembering when ordering steps:

- **The `map` action changes the class names.** Before `map`, the class names
  are the source database tables (eg. `WWMeasure` in ODM v1); after `map`, they
  are the target database tables (eg. `measures` in ODM v3). Any action that
  takes a `schema` parameter must be given the schema that matches the data at
  that point in the pipeline.
- **Some actions merge the list of DataFrames for a class into one.** `filter`
  and `save` concatenate all DataFrames of a class before doing their work.

## Conditional Steps

The `if` key controls whether a step runs. It is evaluated after string
interpolation, and the step runs when the resulting value is the string `true`,
`1`, or `yes` (case-insensitive), a non-zero number, or boolean `True`. If `if`
is absent the step always runs.

The most common use is to run a step only in debug mode, or only outside of it:

```yaml
- action: save
  if: "{debug_mode}"        # only when --debug was passed
  params:
    output_dir: "{temp}/cleaned_data/"
    output_name: "{class_name}[cleaned].csv"

- action: drop_columns
  if: "{not_debug_mode}"    # only when --debug was NOT passed
  params:
    keep_columns_in_schema_only: True
    schema: "{shared}/schemas/odm_v3.yaml"
```

## String Interpolation Variables

String values in `params` (and in `if`) can contain the following interpolation
variables:

| Variable | Value |
| :------- | :---- |
| `{output_dir}` | The output directory, as given by the `--output-dir` command-line option. |
| `{temp}` | The temporary directory. This is either the directory given by `--temp-dir`, or a directory created in the system temporary location and deleted when the pipeline finishes. |
| `{debug_mode}` | `True` when debug mode is enabled (the `--debug` flag), otherwise `False`. |
| `{not_debug_mode}` | The opposite of `{debug_mode}`. |
| `{shared}` | The directory of the `_shared` module, which holds schemas, ID code, and filters shared between modules. Only valid in module-relative path parameters (see below). |
| `{class_name}` | The class/table name that the current DataFrame belongs to. Only available in the `output_name` parameter of the [`save`](save.md) action. |

Not every parameter is interpolated — each action's document lists which of its
parameters support which variables.

## How Paths Are Resolved

Path parameters come in two kinds, and the difference matters when writing a
module:

1. **Module-relative paths** — resolved inside the module directory. These are
   the paths to the module's own files: schemas, mapper directories, filter
   files, ID code files, and action config files. They may start with `{shared}`
   to point into the `_shared` module, or `{temp}` to point into the temporary
   directory (which is how generated files from an earlier step are consumed by
   a later one). A path that resolves outside its base directory (for example
   via `../..`) is rejected with an error.

    ```yaml
    schema: schemas/nwss_reporting.yaml          # inside this module
    target_schema: "{shared}/schemas/odm_v3.yaml" # inside the _shared module
    source_schema: "{temp}/wide_to_long/schema/schema.yaml"  # generated earlier
    ```

2. **Output paths** — ordinary filesystem paths for files the pipeline writes,
   such as `save`'s `output_dir` and `clean`'s `log_file`. These are *not*
   resolved inside the module; they are used as given after interpolation, so
   they normally start with `{output_dir}` or `{temp}`.

    ```yaml
    output_dir: "{output_dir}"
    log_file: "{output_dir}/logs/change_log_input.xlsx"
    ```

When `{shared}` or `{temp}` is used in a module-relative path it must be at the
very start of the path. `"{temp}/mapped_data/"` is valid, while
`"data/{temp}/mapped_data/"` and `"/{temp}/mapped_data/"` are not.

## A Typical Pipeline Order

Actions can be combined in any order, but most modules follow this shape:

1. [`clean`](clean.md) — normalize the input against the **source** schema.
2. [`save`](save.md) *(debug only)* — dump the cleaned input for inspection.
3. [`select_enum_hierarchy`](select_enum_hierarchy.md) *(optional)* — reduce
   multivalued enum cells to their most specific values.
4. [`prepare_wide_to_long`](prepare_wide_to_long.md) *(wide sources only)* —
   restructure wide data and generate its mappers, schema, and ID code.
5. [`map`](map.md) — transform source tables into target tables. **Class names
   change here.**
6. [`expand`](expand.md) *(optional)* — split multivalued cells into rows.
7. [`filter`](filter.md) — drop rows that should not be in the output.
8. [`save`](save.md) *(debug only)* — dump the pre-ID data for inspection.
9. [`generate_ids`](generate_ids.md) — create primary and foreign keys.
10. [`clean`](clean.md) — normalize the output against the **target** schema.
11. [`filter`](filter.md) — drop rows still missing required values.
12. [`drop_columns`](drop_columns.md) *(non-debug only)* — strip internal
    columns.
13. [`save`](save.md) — write the final output.

For complete, working examples read the `config.yaml` of any built-in module in
[/odm_map/data/modules](https://github.com/PHES-ODM/PHES-ODM-Mapper/tree/main/odm_map/data/modules).

## Internal Columns

Several actions refer to two families of internal columns. They are added
automatically during mapping and ID generation, are carried between steps, and
are normally removed by [`drop_columns`](drop_columns.md) before the final
[`save`](save.md):

- **Tracking columns** record which source file, source class, and source row
  each output row was populated from. They are named `(__source_file__)`,
  `(__source_class__)`, `(__source_row__)`, and `(__source_file_and_row__)` —
  that is, any column that starts with `(__` and ends with `__)`. The ID
  generator uses them to link rows between tables.
- **Extra columns** carry temporary non-schema data needed during processing,
  such as tags used for linking. They are any column starting with `_extra_`.

## Related Documentation

| Document | Description |
| :------- | :---------- |
| [reference/reference.md](../reference.md) | The module configuration file, the command line, and the Python API |
| [reference/filters.md](../filters.md) | The filtering rules used by the `filter` action |
| [reference/id_generator.md](../id_generator.md) | The ID code and ID config files used by the `generate_ids` action |
| [reference/wide_to_long_spec.md](../wide_to_long_spec.md) | Wide-format column naming, used by `prepare_wide_to_long` |
