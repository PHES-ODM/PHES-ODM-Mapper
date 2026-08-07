# Action: map

Perform the actual mapping, transforming the data from the source database
format into the target database format using
[LinkML-Map](https://github.com/linkml/linkml-map) schemas.

## Where It Fits

`map` is the centre of a module. Everything before it works on source-format
data; everything after it works on target-format data.

**After this step the class names change** — the keys of the data are no longer
the source tables (eg. `WWMeasure`) but the target tables (eg. `measures`).
Every later action that takes a `schema` parameter must be given the target
schema.

Along with [`generate_ids`](generate_ids.md), this is the most time-consuming
action. Small datasets map in minutes; very large ones can take half a day or
more. Use the `--max-processes` command-line option to map in parallel.

A module may run `map` more than once. The `odm-v3-wide-to-long` module runs
[`prepare_wide_to_long`](prepare_wide_to_long.md) and then `map`, consuming the
schema and mappers that were generated into the temporary directory.

## Example

```yaml
- action: map
  params:
    source_schema: schemas/nwss_reporting.yaml
    target_schema: "{shared}/schemas/odm_v3.yaml"
    mappers_dir: mappers
```

Consuming generated artifacts from an earlier step:

```yaml
- action: map
  params:
    source_schema: "{temp}/wide_to_long/schema/schema.yaml"
    target_schema: "{shared}/schemas/odm_v3.yaml"
    mappers_dir: "{temp}/wide_to_long/"
```

## Parameters

| Parameter | Required/Optional | Description |
| :-------- | :---------------- | :---------- |
| `source_schema` | Required | The LinkML schema of the data being mapped **from**. Module-relative path; may start with `{shared}` or `{temp}`. |
| `target_schema` | Required | The LinkML schema of the data being mapped **to**. Module-relative path; may start with `{shared}` or `{temp}`. |
| `mappers_dir` | Required | The directory containing the LinkML-Map schemas that define the mapping. Every YAML file in the directory is used. Module-relative path; may start with `{shared}` or `{temp}`. |
| `prepare_bar_title` | Optional | Title of the progress bar shown while preparing the data before mapping. Defaults to `Preparing IDs`. |
| `map_bar_title` | Optional | Title of the progress bar shown while mapping. Defaults to `Initial Mapping`. |

> The parameter name is `mappers_dir` (plural "mappers"). A missing or misspelled
> name leaves it unset and the mapping will fail.

`source_schema` is a separate parameter from the module's top-level
`source_schema` key. The top-level key tells the pipeline which tables the input
files may belong to; this parameter tells the mapper what the data looks like at
this step. For the first `map` step in a module they are usually the same file.

## Preparing the LinkML Schemas

At a minimum the source and target databases each need a LinkML schema. Each
schema must:

- define a class for every table in the database, with the table's columns as
  attributes,
- define the enumerations used by those columns, and
- define a **tree root** class whose slots are the names of all the database
  tables.

The built-in schemas in
[/odm_map/data/modules/_shared/schemas](/odm_map/data/modules/_shared/schemas)
are good models to follow. Schemas used by more than one module belong in the
`_shared` module and are referenced with `{shared}`.

## Preparing the Mapper Files

`mappers_dir` holds the mapping schemas. Every YAML file in the directory is
loaded, and the outputs from all of them are concatenated per target
table/class, so a mapping can be split across as many files as is convenient.
The built-in modules use one file per source-table variant, which keeps each
file small and readable.

Each file must be a valid LinkML-Map YAML file, and two rules apply:

1. In `class_derivations`, each top-level key must be the name of a class in the
   **target** database. Optional text in square brackets may follow the class
   name and is ignored, which is how several derivations can populate the same
   target class from one file (eg. `measures[001]` populates `measures`).
2. There must be a class derivation for the **tree root** class of the target
   schema, and its slot derivations must name every target class derivation in
   that file (eg. `measures[001]` from the example above).

The following mapper file populates the ODM v2/v3 `measures` table from the ODM
v1 `WWMeasure` table, with `Container` as the tree root of the target schema:

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

Tracking columns are handled for you: the mapper adds slot derivations that copy
the tracking columns (source file, class, and row) through to the output, so
[`generate_ids`](generate_ids.md) can link rows between tables afterwards. Do
not write derivations for them yourself.

For working examples, see the `mappers` directory of any built-in module, such
as
[/odm_map/data/modules/odm-v1-to-v2/mappers](/odm_map/data/modules/odm-v1-to-v2/mappers).

> **⚠️ Security note:** Mapper files may use LinkML-Map `expr` slot derivations,
> and the Mapper evaluates these expressions in _unrestricted_ mode by default.
> This means an `expr` string can execute arbitrary Python code while mapping.
> Only run modules you trust. Treat a module directory or ZIP (including any
> module supplied via `--module-path`) as executable code, not just
> configuration — never run a module from an untrusted source without
> reviewing its mapper files first.

## Related Documentation

- [Pipeline Actions](README.md) — step structure, interpolation variables, and
  path resolution
- [Reference](../reference.md#module-configuration) — the module
  configuration file
- [prepare_wide_to_long](prepare_wide_to_long.md) — generates a source schema
  and mapper files for a downstream `map` step
- [generate_ids](generate_ids.md) — the step that links the mapped tables
  together
- Implementation:
  [/odm_map/actions/action_map_data.py](/odm_map/actions/action_map_data.py),
  [/odm_map/mapper/map_data.py](/odm_map/mapper/map_data.py)
