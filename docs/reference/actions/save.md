# Action: save

Write the current data to disk as CSV files, one file per class/table.

## Where It Fits

`save` is the last step of a module, writing the final mapped output to the
directory given by `--output-dir`. It is also used **between** steps to dump
intermediate data for inspection; those intermediate saves are guarded with
`if: "{debug_mode}"` so they only happen in a debug run.

`save` does not change the data — the step after it receives exactly what the
step before it produced — so a debug save can be dropped in anywhere without
affecting the result. All DataFrames belonging to a class are concatenated into
one file.

## Example

The final save of a module:

```yaml
- action: save
  params:
    output_dir: "{output_dir}"
    output_name: "{class_name}.csv"
    progress_bar_title: Saving Data
```

An intermediate save, only in debug mode:

```yaml
- action: save
  if: "{debug_mode}"
  params:
    output_dir: "{temp}/mapped_data/"
    output_name: "{class_name}[preid].csv"
```

## Parameters

| Parameter | Required/Optional | Description |
| :-------- | :---------------- | :---------- |
| `output_dir` | Required | The directory to save to. This is an output path (not module-relative) and supports the `{output_dir}`, `{temp}`, `{debug_mode}`, and `{not_debug_mode}` variables. |
| `output_name` | Required | The file name for each saved file. Supports the same variables as `output_dir` plus `{class_name}`, the class/table name the data belongs to. |
| `progress_bar_title` | Optional | Title of the progress bar shown while saving. If omitted, no progress bar is shown. |

## Preparing `output_dir` and `output_name`

`output_name` is applied per class, so it must produce a distinct name for each
one — in practice it must contain `{class_name}`. Without it every class would
be written to the same file, each overwriting the last.

`{class_name}` is only available in `output_name`, not in `output_dir`.

Some useful patterns:

| `output_dir` | `output_name` | Result |
| :----------- | :------------ | :----- |
| `"{output_dir}"` | `"{class_name}.csv"` | The final output: `measures.csv`, `samples.csv`, … in the `--output-dir` directory. |
| `"{temp}/cleaned_data/"` | `"{class_name}[cleaned].csv"` | Intermediate data in the temporary directory, tagged so its pipeline position is obvious. |
| `"{output_dir}/intermediate/"` | `"{class_name}[preid].csv"` | Intermediate data kept next to the final output rather than in the temporary directory. |

Missing directories are created automatically. Files are **overwritten** without
warning if they already exist, so give each `save` step in a module a distinct
directory or a distinct `output_name` tag.

Note that data written under `{temp}` is deleted when the pipeline finishes
unless `--temp-dir` was used to name a directory explicitly. To keep debug
output around, either run with `--temp-dir` or write the intermediate saves
under `{output_dir}` instead.

## Related Documentation

- [Pipeline Actions](README.md) — step structure, interpolation variables, and
  path resolution
- [drop_columns](drop_columns.md) — the step that normally precedes the final
  save
- [Reference](../reference.md#module-configuration) — the module
  configuration file
- Implementation:
  [/odm_map/actions/action_save_data.py](https://github.com/PHES-ODM/PHES-ODM-Mapper/blob/main/odm_map/actions/action_save_data.py)
