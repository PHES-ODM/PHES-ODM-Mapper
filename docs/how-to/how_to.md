# How-To Guides

Each section here solves one problem. They assume you have already run a mapping
— if you have not, work through the [tutorial](../tutorials/tutorial.md) first. For the
command that performs each built-in conversion, see [Supported
Mappings](https://github.com/PHES-ODM/PHES-ODM-Mapper/blob/main/README.md#supported-mappings).

- [Choose which files and tables to map](#choose-which-files-and-tables-to-map)
- [Map data spread over several files](#map-data-spread-over-several-files)
- [Map data from an Excel workbook](#map-data-from-an-excel-workbook)
- [Run a mapping from Python](#run-a-mapping-from-python)
- [Run a mapping in a Jupyter notebook](#run-a-mapping-in-a-jupyter-notebook)
- [Speed up a large mapping](#speed-up-a-large-mapping)
- [Debug a mapping that produced the wrong output](#debug-a-mapping-that-produced-the-wrong-output)
- [Use a custom module](#use-a-custom-module)
- [Create a custom module](#create-a-custom-module)
- [Distribute a module as a ZIP file](#distribute-a-module-as-a-zip-file)

## Choose which files and tables to map

Every input file must be attributed to a table in the source format. The Mapper
does that by name, so you usually only need to name your files after the tables
they hold.

**Point it at a directory** to map every recognized file inside it:

```console
odm-map --module odm-v1-to-v3 --output-dir "output" "path/to/inputdata"
```

Files with recognized extensions (`.csv`, `.tsv`, `.txt`, `.xlsx`) are matched
against the source format's table names. Anything not matching a table is
ignored with a warning, so unrelated files in the directory are harmless.

The match ignores the extension and any text from the first opening square or
round bracket onward, then takes the longest source table name found in what
remains, case-insensitively. So all of these load the `WWMeasure` table:

```text
WWMeasure.csv
WWMeasure[2024-12-20].csv
1. WWMeasure (Ottawa).xlsx
```

**Name the table explicitly** when a file cannot be renamed, by prefixing the
path with the table name and a colon:

```console
odm-map \
    --module odm-v1-to-v3 \
    --output-dir "output" \
    "WWMeasure:path/to/measurements-export.csv"
```

An explicit prefix is matched case-sensitively and must be an exact table name,
so a typo is reported as an error rather than silently ignored. The prefix works
for `.csv`, `.tsv`, and `.txt` files.

If no input file matches any table, the run stops and lists the table names the
source format recognizes.

## Map data spread over several files

List the files individually. Several files can belong to the same table; they
are all loaded into it:

```console
odm-map \
    --module odm-v1-to-v3 \
    --output-dir "output" \
    "WWMeasure:path/to/measures-2023.csv" \
    "WWMeasure:path/to/measures-2024.csv" \
    "path/to/Sample.csv"
```

Directories and files can be mixed in the same command, so you can map a
directory and add a file from elsewhere in one run.

## Map data from an Excel workbook

Pass the workbook as an input. Each sheet tab is matched to a table using the
same naming rules as file names, and sheets that match no table are skipped:

```console
odm-map --module pha4ge-to-v3 --output-dir "output" "path/to/data.xlsx"
```

A single workbook holding one sheet per table is therefore enough for a whole
mapping. The table-name prefix (`WWMeasure:...`) does not apply to Excel files —
rename the sheet tab instead.

## Run a mapping from Python

Use the `Pipeline` class instead of the command line when you want to map from a
script, or to work with the resulting DataFrames directly:

```python
from odm_map.pipeline import Pipeline

pipeline = Pipeline(module="odm-v1-to-v3", module_path=None)

tables = pipeline.run(
    data_files={
        "WWMeasure": ["path/to/wwmeasure.csv"],
        "Sample": ["path/to/sample.csv"],
    },
    output_dir="path/to/output",
)
```

Unlike the command line, `data_files` states the table for each file directly,
so file names do not matter. `run()` writes the same CSV files as the CLI and
also returns a `dict` of table name to list of DataFrames, ready for further
analysis:

```python
measures = tables["measures"][0]
print(measures.shape)
```

To read a sheet from an Excel workbook, give a dictionary instead of a path:

```python
data_files = {
    "PHA4GE": [{"excel_file": "path/to/data.xlsx", "sheet": "PHA4GE"}],
}
```

Every parameter of `run()` is listed in [reference/reference.md](../reference/reference.md#python-api).

## Run a mapping in a Jupyter notebook

Pass `multi_bar_progress=False` so the progress display uses a single bar, which
renders correctly in a notebook:

```python
pipeline.run(
    data_files=data_files,
    output_dir="path/to/output",
    multi_bar_progress=False,
)
```

The command-line tool detects IPython and does this for itself.

## Speed up a large mapping

Mapping is CPU-bound and, for large datasets, memory-hungry. In rough order of
effect:

1. **Map on more than one process.** The mapping step splits each table into
   chunks and maps the chunks in parallel:

    ```console
    odm-map \
        --module nwss-reporting-to-v3 \
        --max-processes 8 \
        --output-dir "output" \
        "path/to/nwss.csv"
    ```

    A non-positive value uses every available processor. The default is `1`,
    which maps without multiprocessing.

2. **Put the temporary directory on fast storage.** Intermediate data is written
   between steps, and on a large run it is substantial. A RAM disk or SSD helps:

    ```console
    odm-map ... --temp-dir "/path/to/fast/disk/odm-temp"
    ```

    Note that a directory given with `--temp-dir` is *not* deleted afterwards.

3. **Do not run with `--debug`.** Debug mode retains internal columns and
   duplicate rows and saves extra intermediate files, all of which cost time and
   space.

4. **Try it on a slice first.** `--max-rows 1000` confirms the mapping is
   configured correctly before you commit hours to the full dataset.

See [Performance](../explanation/explanation.md#performance) for what makes a run expensive.

## Debug a mapping that produced the wrong output

Work outward from the output:

1. **Read the change log.** The cleaning step writes
   `<output-dir>/logs/change_log_input.xlsx`, recording every correction it made
   to the input — corrected enumeration values, renamed columns, values that
   failed a pattern check. Wrong or missing values in the output are very often
   explained here.

2. **Re-run with `--debug` and `--temp-dir`.**

    ```console
    odm-map \
        --module odm-v1-to-v3 \
        --output-dir "output/debug" \
        --temp-dir "output/temp" \
        --max-rows 500 \
        --debug \
        "path/to/inputdata"
    ```

    The output keeps its internal columns, including `(__source_file__)` and
    `(__source_row__)` which identify the input row each output row came from,
    and the ID columns as they were before ID generation. Rows that would have
    been dropped for having duplicate primary keys are retained and flagged.

3. **Inspect the intermediate files** in the temporary directory. Modules save
   the data after cleaning and again before ID generation, which localizes the
   problem to one step: if a value is already wrong in the cleaned data the
   cause is in the input or the `clean` step, and if it is right there but wrong
   afterwards the cause is in the mapping.

4. **Read the document for the step at fault.** Each action's document describes
   its parameters and the files it reads — see [actions/](../reference/actions).

## Use a custom module

Give `--module-path` the module's directory instead of naming a built-in module
with `--module`:

```console
odm-map \
    --module-path "path/to/my-module" \
    --output-dir "output" \
    "path/to/inputdata"
```

Exactly one of `--module` and `--module-path` may be given. From Python, pass
`module=None` and set `module_path`:

```python
pipeline = Pipeline(module=None, module_path="path/to/my-module")
```

## Create a custom module

A module is a directory holding a `config.yaml` and the files its steps refer
to. To build one for a source format that is not supported:

1. **Write LinkML schemas for the source and target formats.** Each schema
   defines the format's tables and enumerations, and has a tree root class whose
   slots are the table names. If your target is ODM, reuse the schema already in
   the `_shared` module rather than writing one.

2. **Create the module directory** and give it a `config.yaml` with `title`,
   `source_schema`, and `steps`. The [module
   reference](../reference/reference.md#module-configuration) describes each key, and
   [actions/README.md](../reference/actions/README.md) covers step structure, the `if` key,
   the interpolation variables, and the order actions are usually combined in.

3. **Add the steps your conversion needs.** Most modules clean the input, map
   it, filter it, generate IDs, and save — see [A typical pipeline
   order](../reference/actions/README.md#a-typical-pipeline-order). Each action has its own
   document under [actions/](../reference/actions) explaining its parameters and how to
   prepare the files it reads.

4. **Add those files** in subdirectories: `mappers/` for the LinkML-Map files,
   `filters/` for filter rules, `ids/` for ID code and config, and so on. The
   layout is given in [Module directory
   layout](../reference/reference.md#module-directory-layout). Reference shared files with
   the `{shared}` prefix.

5. **Test it on a small slice**, with debugging turned on:

    ```console
    odm-map \
        --module-path "path/to/my-module" \
        --output-dir "output/test" \
        --temp-dir "output/test-temp" \
        --max-rows 100 \
        --debug \
        "path/to/inputdata"
    ```

The built-in modules at [/odm_map/data/modules](https://github.com/PHES-ODM/PHES-ODM-Mapper/tree/main/odm_map/data/modules)
are complete working examples; starting from the one whose shape is closest to
your conversion is usually quicker than starting from nothing. To contribute a module
back as a built-in one, see [CONTRIBUTING.md](https://github.com/PHES-ODM/PHES-ODM-Mapper/blob/main/CONTRIBUTING.md).

## Distribute a module as a ZIP file

Compress the module's root directory into a ZIP file and share that. It is used
exactly like a directory:

```console
odm-map \
    --module-path "path/to/my-module.zip" \
    --output-dir "output" \
    "path/to/inputdata"
```
