# Action: drop_columns

Remove columns from the data. This can drop the internal tracking and `_extra_`
columns added during mapping and ID generation, or reduce every table to only
the columns recognized by a LinkML schema.

## Where It Fits

`drop_columns` is normally the second-to-last step, immediately before the final
[`save`](save.md), because the columns it removes are needed by the steps before
it — [`generate_ids`](generate_ids.md) in particular relies on the tracking
columns to link rows between tables.

It is almost always guarded with `if: "{not_debug_mode}"`, so that a debug run
retains the internal columns for inspection while a normal run produces clean
output.

## Example

The form used by the built-in modules:

```yaml
- action: drop_columns
  if: "{not_debug_mode}"
  params:
    keep_columns_in_schema_only: True
    schema: "{shared}/schemas/odm_v3.yaml"
```

Dropping only the internal columns, keeping everything else:

```yaml
- action: drop_columns
  if: "{not_debug_mode}"
  params:
    drop_tracking_columns: True
    drop_extra_columns: True
```

## Parameters

| Parameter | Required/Optional | Description |
| :-------- | :---------------- | :---------- |
| `keep_columns_in_schema_only` | Optional | If True, keep only the columns that are valid for the class according to `schema`, dropping everything else. Defaults to False. |
| `drop_extra_columns` | Optional | If True, drop all `_extra_` columns. Defaults to False. |
| `drop_tracking_columns` | Optional | If True, drop all tracking columns — the columns recording the source file, class, and row each output row came from. Defaults to False. |
| `schema` | Optional | The LinkML schema to use when `keep_columns_in_schema_only` is True. Required in that case; ignored otherwise. Module-relative path; may start with `{shared}` or `{temp}`. |

This action has no configuration file of its own — the parameters above are the
whole configuration. The only related file is the LinkML schema, which is
normally the target schema already used by [`map`](map.md) and
[`generate_ids`](generate_ids.md).

## Choosing Between the Two Modes

The two modes are mutually exclusive, and this is the one behaviour to be
careful about:

> **`keep_columns_in_schema_only` takes precedence.** When it is True,
> `drop_extra_columns` and `drop_tracking_columns` are **ignored** — the schema
> decides everything. Tracking and `_extra_` columns are dropped anyway in this
> mode, since they are not in the schema.

So:

- **`keep_columns_in_schema_only: True`** — produces output that exactly matches
  the target schema: internal columns are gone, and so is any other column the
  schema does not define. Requires `schema`. Without it the run stops with an
  error. This is what the built-in modules use.
- **`drop_extra_columns` / `drop_tracking_columns`** — surgical removal of only
  the internal columns, leaving any other non-schema column in place. Use this
  when the output is intended to carry extra columns beyond the schema. No
  `schema` is needed.

## Related Documentation

- [Pipeline Actions](README.md) — step structure, interpolation variables, and a
  description of the tracking and `_extra_` columns
- [save](save.md) — the step that normally follows
- [Reference](../reference.md#module-configuration) — the module
  configuration file
- Implementation:
  [/odm_map/actions/action_drop_columns.py](https://github.com/PHES-ODM/PHES-ODM-Mapper/blob/main/odm_map/actions/action_drop_columns.py),
  [/odm_map/column_dropper/drop_columns.py](https://github.com/PHES-ODM/PHES-ODM-Mapper/blob/main/odm_map/column_dropper/drop_columns.py)
