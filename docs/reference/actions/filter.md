# Action: filter

Remove rows that should not be in the output — for example rows with a missing
required `value`, or rows carrying a sentinel value such as `<ignore>`.

## Where It Fits

`filter` is normally run after [`map`](map.md), since mapping a wide source into
long tables commonly produces rows with missing or placeholder values. Modules
often use it more than once:

- Right after `map` (and after [`expand`](expand.md), if present) to drop rows
  that are empty or explicitly ignored.
- After [`generate_ids`](generate_ids.md) to drop rows still missing required
  values, once IDs have had their chance to fill slots in. The built-in modules
  do this with the shared filter file
  [`{shared}/filters/odm_vx_filter_required_values.csv`](https://github.com/PHES-ODM/PHES-ODM-Mapper/blob/main/odm_map/data/modules/_shared/filters/odm_vx_filter_required_values.csv).

Before filtering, all DataFrames belonging to a class are concatenated into a
single DataFrame, and each class ends up with exactly one DataFrame afterwards.

The `class` and `slot` names in the filter file refer to the data as it exists
at that step — source names before `map`, target names after it.

## Example

```yaml
- action: filter
  params:
    filters: filters/nwss_reporting_to_v3_filters.csv
```

Dropping rows normally, but marking them instead of dropping them in debug mode:

```yaml
- action: filter
  params:
    filters: "{shared}/filters/odm_vx_filter_required_values.csv"
    mark_instead_of_drop: "{debug_mode}"
```

## Parameters

| Parameter | Required/Optional | Description |
| :-------- | :---------------- | :---------- |
| `filters` | Required | A CSV or Excel file containing the filtering rules. For an Excel file the first sheet is used. Module-relative path; may start with `{shared}` or `{temp}`. |
| `mark_instead_of_drop` | Optional | If true, rows are not dropped — instead the `____drop` column is set to `True` for them. Defaults to `False`. Normally set to `"{debug_mode}"` so that dropped rows can be reviewed in debug runs. |

## Preparing the Filter File

The filter file is a table — CSV, or the first sheet of an Excel workbook — with
one rule per row and the columns `inputFilter`, `outputFilter`, `class`, `slot`,
`operation`, and `value`. Rules are applied top to bottom.

The example below drops every row in the `measures` table where `measure` or
`unit` is `<ignore>`, or where `value` is blank or `-1`, and does something
similar for `protocolSteps`:

| inputFilter | outputFilter | class         | slot       | operation      | value         |
| :---------- | :----------- | :------------ | :--------- | :------------- | :------------ |
|             | 0            | measures      |            | create_filter  | TRUE          |
| 0           | 0            | measures      | measure    | exclude_equals | \<ignore\>    |
| 0           | 0            | measures      | unit       | exclude_equals | \<ignore\>    |
| 0           | 0            | measures      | value      | exclude_equals | ["", -1]      |
| 0           |              | measures      |            | apply_filter   | measures      |
|             | 1            | protocolSteps |            | create_filter  | TRUE          |
| 1           | 1            | protocolSteps | measure    | exclude_equals | \<ignore\>    |
| 1           | 1            | protocolSteps | method     | exclude_equals | \<ignore\>    |
| 1           | 1            | protocolSteps | value      | exclude_equals |               |
| 1           |              | protocolSteps |            | apply_filter   | protocolSteps |

In outline: a **named boolean filter** is created for a class, one operation per
row narrows it, and a final `apply_filter` row actually applies it to the
DataFrame. Most operations only change the filter, not the data, so a filter
file that never calls `apply_filter` changes nothing.

[Filtering](../filters.md) is the complete reference: the meaning of each column,
how filters are named and combined, and every available operation
(`create_filter`, `exclude_equals`, `include_equals`, `requires_any`,
`requires_all`, `drop_duplicates`, `and_filters`, `or_filters`, `invert_filter`,
`copy_filter`, `delete_filter`, `copy_class`, `delete_class`, and
`apply_filter`). Read it before writing a filter file.

Practical points when preparing the file:

- Give a module one filter file per pipeline position rather than one large file
  for everything. The `pha4ge-to-v3` module has separate files for dropping
  empty samples and for its pre-ID filtering, run as two consecutive `filter`
  steps.
- Put filter files that several modules share in the `_shared` module and
  reference them with `{shared}`.
- The `value` column is parsed as YAML, so `["", -1]` is a two-item list and
  JSON syntax works too.

## Debug Mode and the `____drop` Column

With `mark_instead_of_drop` set to true, `apply_filter` keeps every row and
instead adds a `____drop` column set to `True` on the rows that would have been
dropped. This makes it possible to open the final output and see exactly which
rows a normal run would have removed, and why.

Because this changes the output columns, set it from `{debug_mode}` rather than
hard-coding it to true:

```yaml
mark_instead_of_drop: "{debug_mode}"
```

Note that a filter step whose purpose is structural — for example one that
reduces several candidate rows to the correct one before ID generation — should
normally drop rows even in debug mode, so leave `mark_instead_of_drop` unset
there.

## Related Documentation

- [Pipeline Actions](README.md) — step structure, interpolation variables, and
  path resolution
- [Filtering](../filters.md) — the complete filter file and operation reference
- [Reference](../reference.md#module-configuration) — the module
  configuration file
- Implementation:
  [/odm_map/actions/action_filter_data.py](https://github.com/PHES-ODM/PHES-ODM-Mapper/blob/main/odm_map/actions/action_filter_data.py),
  [/odm_map/filter/filter_data.py](https://github.com/PHES-ODM/PHES-ODM-Mapper/blob/main/odm_map/filter/filter_data.py),
  [/odm_map/filter/filter_funcs.py](https://github.com/PHES-ODM/PHES-ODM-Mapper/blob/main/odm_map/filter/filter_funcs.py)
