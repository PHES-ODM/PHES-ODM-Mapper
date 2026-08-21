# Action: clean

Normalize data against a LinkML schema: fix column names, correct the
capitalization and spacing of enumeration values, add ontology IDs to
enumeration values, and report values that do not match the patterns in the
schema. Changes can be written to a log file so they can be reviewed.

## Where It Fits

`clean` is normally the **first** step of a module, run against the **source**
schema, so that later steps can rely on correct column names and enumeration
values. Most modules also run it **after** [`map`](map.md) (and after
[`generate_ids`](generate_ids.md), if ID generation depends on values that the
cleaner would otherwise remove) against the **target** schema, to normalize the
mapped output.

The `schema` parameter must always match the format the data is in at that point
in the pipeline. Using a target schema before `map`, or a source schema after
it, means nothing will be recognized and every column will be dropped.

## Example

```yaml
- action: clean
  params:
    schema: schemas/pha4ge.yaml
    log_file: "{output_dir}/logs/change_log_input.xlsx"
    operations:
      - format_and_match_columns: [ lowercase, { remove_chars: "-"}, alpha_numeric_underscore, single_underscores, trim_trailing_underscores ]
      - add_ontology_ids_to_enums:
          match_ontology_id: "\\[[A-Za-z0-9_]+:[A-Za-z0-9_]+\\]$"
      - correct_enums: True
      - check_patterns: True
```

## Parameters

| Parameter | Required/Optional | Description |
| :-------- | :---------------- | :---------- |
| `schema` | Required | Path to the LinkML schema the data currently belongs to. This is a module-relative path and may start with `{shared}` or `{temp}`. |
| `log_file` | Optional | If given, all changes and warnings are written to this file. Must be an Excel (`.xlsx`) or CSV (`.csv`) file. This is an output path (not module-relative) and supports the `{output_dir}`, `{temp}`, `{debug_mode}`, and `{not_debug_mode}` variables. See [The Log File](#the-log-file) below. |
| `operations` | Required | An ordered list of cleaning operations to perform. Each list item is a dictionary with exactly one key: the operation name, whose value is that operation's parameter(s). |

## Preparing the `operations` List

`operations` is a YAML list, and each item must have exactly **one** key. More
than one key in a single item raises an error, so keep each operation on its own
list item:

```yaml
operations:
  - format_and_match_columns: True     # correct
  - correct_enums: True                # correct
```

```yaml
operations:
  - format_and_match_columns: True     # WRONG — two keys in one list item
    correct_enums: True
```

Operations run **in the order they are listed**, and the order matters:

- `format_and_match_columns` should come first. The other operations look up
  slots by column name in the schema, so they only work once the column names
  have been matched to the schema.
- `add_ontology_ids_to_enums` should come before `correct_enums`.
  `correct_enums` clears enumeration values it cannot recognize, and a value
  that is still missing its ontology ID may not be recognized.
- `check_patterns` makes no changes, so it can go anywhere, but it is most
  useful last, once the values are in their final form.

The four available operations are described below.

### Clean Operation: format_and_match_columns

Format the column names, then match them against the valid column names for the
class in the schema. Matching is case-insensitive and happens after formatting.
A column that cannot be matched is dropped, and a column that exists in the
schema but not in the data is added with empty values.

```yaml
operations:
  - format_and_match_columns: [ lowercase, { remove_chars: "-"}, alpha_numeric_underscore, single_underscores, trim_trailing_underscores ]
```

The value is a list of formatting operations, applied to every column name in
the order listed:

| Formatting option | Effect |
| :---------------- | :----- |
| `lowercase` | Make the column name lowercase. |
| `uppercase` | Make the column name uppercase. |
| `alpha_numeric_underscore` | Replace every non-alphanumeric character with an underscore. |
| `single_underscores` | Collapse runs of underscores into one (`column__name` → `column_name`). |
| `trim_trailing_underscores` | Remove trailing underscores (`_column_name__` → `_column_name`). |
| `trim_whitespace` | Remove leading and trailing whitespace. |
| `remove_special` | Remove every character that is not alphanumeric or whitespace. |
| `{ remove_chars: "chars" }` | Remove every character found in the string `chars`. |

An unrecognized formatting option stops the run with an error.

If no formatting is needed, but columns should still be matched to the schema
case-insensitively (with unrecognized columns dropped and missing columns
added), set the operation to `True`:

```yaml
operations:
  - format_and_match_columns: True
```

Notes:

- Tracking and `_extra_` columns are never formatted and never dropped.
- If two source columns normalize to the same schema column, the first is kept
  and the later one is dropped, and the drop is recorded in the log.
- If the class itself is not in the schema, the columns for that class are left
  untouched.

### Clean Operation: correct_enums

Correct the capitalization and spacing of every enumeration value in the data so
that it matches the permissible value in the schema.

```yaml
operations:
  - correct_enums: True
```

For example, if the data contains `degrees celsius` in a slot whose range is an
enumeration with the permissible value `Degrees Celsius`, the value in the data
is replaced with `Degrees Celsius`.

When matching, capitalization is ignored and runs of multiple spaces are treated
as a single space, but the value written back to the data uses exactly the
capitalization and spacing from the schema.

> **Note:** values that cannot be matched to any permissible value are
> **cleared** (set to empty) and reported in the log under *Unrecognized enum
> values*. If a later step depends on a value that is deliberately not a valid
> enumeration value — for example a tag such as `sampleShed:corFcil` that
> [`generate_ids`](generate_ids.md) will process — run that step **before** this
> `clean` step. The `pha4ge-to-v3` module does exactly this, and its
> `config.yaml` carries a comment explaining why.

### Clean Operation: add_ontology_ids_to_enums

Add ontology IDs to enumeration values in the data, where the schema's
permissible values have them.

```yaml
operations:
  - add_ontology_ids_to_enums:
      match_ontology_id: "\\[[A-Za-z0-9_]+:[A-Za-z0-9_]+\\]$"
```

| Parameter | Required/Optional | Description |
| :-------- | :---------------- | :---------- |
| `match_ontology_id` | Required | A regular expression that matches the ontology ID portion of a permissible value in the schema. It must be present and must be a string, otherwise the run stops with an error. |

For example, if the schema has the permissible value `degree Celsius (C)
[UO:0000027]` and the data contains `degree Celsius (C)`, then the data value
becomes `degree Celsius (C) [UO:0000027]`. The regular expression is used to
strip the ID from the schema's permissible values so that the remainder can be
matched against the data. As with `correct_enums`, capitalization and repeated
spaces are ignored when matching.

Values that cannot be matched are left unchanged by this operation (they are not
cleared, and not logged).

### Clean Operation: check_patterns

Check every value in the data against the regex `pattern` defined for its slot
in the LinkML schema, and report any value that does not match. This operation
makes no changes to the data.

```yaml
operations:
  - check_patterns: True
```

Mismatches are reported in the log under *Mismatch pattern*.

## The Log File

If `log_file` is set, the changes and warnings from the cleaning operations are
written there. The following logs are produced (only non-empty ones are
written):

| Log name | Contents |
| :------- | :------- |
| `Unrecognized enum values` | Values that did not match any permissible value and were cleared. |
| `Mismatch pattern` | Values that did not match the slot's regex pattern (from `check_patterns`). |
| `Added ontology IDs` | Values that had an ontology ID appended. |
| `Correct caps and spacing` | Values whose capitalization or spacing was corrected. |
| `Column name changes` | Columns that were renamed to match the schema. |
| `Columns removed` | Columns that were dropped as unrecognized or as duplicates. |
| `Columns missing` | Schema columns that were absent from the data and added as empty. |

The file format determines how the logs are laid out:

- **Excel (`.xlsx`)** — each log becomes its own worksheet tab. Do not include
  `{log_name}` in the file name.

    ```yaml
    log_file: "{output_dir}/logs/change_log_input.xlsx"
    ```

- **CSV (`.csv`)** — each log becomes its own file, so the file name **must**
  contain `{log_name}`, which is replaced by the log name in lowercase with
  non-alphanumeric characters converted to underscores. For example,
  `clean_log-{log_name}.csv` produces `clean_log-unrecognized_enum_values.csv`.

    ```yaml
    log_file: "{output_dir}/logs/clean_log-{log_name}.csv"
    ```

Directories in the path are created automatically. If a module runs `clean` more
than once, give each step a different `log_file` (or omit it) so that the logs
are not overwritten. When there is nothing to report, a single log containing
"Nothing to report" is written.

## Related Documentation

- [Pipeline Actions](README.md) — step structure, interpolation variables, and
  path resolution
- [Reference](../reference.md#module-configuration) — the module
  configuration file
- Implementation:
  [/odm_map/actions/action_clean_data.py](../../odm_map/actions/action_clean_data.py),
  [/odm_map/cleaner/clean_data.py](../../odm_map/cleaner/clean_data.py)
