# Tutorial: Your First Mapping

This tutorial takes you through one complete mapping from beginning to end. You
will download a real ODM v1 dataset, convert it to ODM v3, and look at what
came out. It should take about fifteen minutes, plus mapping time.

You do not need to understand the Mapper's internals to follow along — every
command is given in full. When you want to know *why* something happens, read
[How the Mapper Works](../explanation/explanation.md) afterwards.

## What you need

- Python 3.10 or higher.
- The Mapper installed (`pip install
  git+https://github.com/PHES-ODM/PHES-ODM-Mapper.git`). See
  [Installation](https://github.com/PHES-ODM/PHES-ODM-Mapper/blob/main/README.md#installation).
- `git`, to fetch the sample data.

Check that the Mapper is installed:

```console
odm-map --help
```

This prints the available options and the list of installed conversion modules.
If the command is not found, revisit the installation step.

## Step 1: Get the sample data

The Ottawa Wastewater Surveillance Consortium publishes ODM v1 data that is
ideal for a first run. Clone it:

```console
git clone git@github.com:OntarioWastewaterSurveillanceConsortium/sars-cov-2-data.git
```

The datasets live under the `CSV` directory, one directory per location. Look
inside the Ottawa one:

```console
ls sars-cov-2-data/CSV/Ottawa
```

You will see CSV files named after ODM v1 tables — `Sample.csv`,
`WWMeasure.csv`, `Site.csv`, and so on. Those names are how the Mapper knows
which source table each file belongs to.

## Step 2: Run a small mapping first

Mapping the whole dataset can take a while, so start with a small slice. The
`--max-rows` option limits how many rows are read from each input file:

```console
odm-map \
    --module odm-v1-to-v3 \
    --output-dir "output/v3-sample" \
    --max-rows 500 \
    "sars-cov-2-data/CSV/Ottawa"
```

Three things are happening in that command:

- `--module odm-v1-to-v3` selects the conversion. The module name says what it
  converts from and to.
- `--output-dir` is where the resulting CSV files are written. It is created if
  it does not exist.
- The final argument is the input. Directories are scanned for recognized
  files; you can also list individual files.

As it runs, progress bars show each stage. This module cleans the input, maps it
to the target format, cleans the result, generates IDs, and saves — the stages
differ from module to module, because each module defines its own sequence. A
first run also spends time loading the LinkML schemas, so give it a moment
before the first bar appears.

## Step 3: Look at the output

```console
ls output/v3-sample
```

Each file is one ODM table in the target format — `measures.csv`,
`samples.csv`, `sites.csv`, and others. Open `measures.csv`. Two things are
worth noticing:

- The **column names and values are ODM v3 names**, not the ODM v1 ones you saw
  in the input. Where ODM v1 had a `WWMeasure` table, the output has `measures`.
- The **ID columns are filled in**. `measureRepID` uniquely identifies each
  measure row, and `sampleID` points at a row in `samples.csv`. The Mapper
  generated these keys so the output tables link to each other; nothing in the
  ODM v1 input had to provide them.

## Step 4: Run the full mapping

Now drop `--max-rows` and let it map everything:

```console
odm-map \
    --module odm-v1-to-v3 \
    --output-dir "output/v3" \
    "sars-cov-2-data/CSV/Ottawa"
```

This dataset takes a few minutes. Larger datasets take considerably longer —
see [Performance](../explanation/explanation.md#performance) for what drives the cost and
[Speed up a large mapping](../how-to/how_to.md#speed-up-a-large-mapping) for what to do
about it.

## Step 5: See what the Mapper did

Two options make a run inspectable. `--debug` adds detail to the output, and
`--temp-dir` keeps the intermediate files instead of deleting them:

```console
odm-map \
    --module odm-v1-to-v3 \
    --output-dir "output/v3-debug" \
    --temp-dir "output/v3-temp" \
    --max-rows 500 \
    --debug \
    "sars-cov-2-data/CSV/Ottawa"
```

Open `output/v3-debug/measures.csv` again. It now carries extra columns showing
the ID values as they were *before* ID generation, along with the primary key
index used for linking — so you can see how each key was arrived at. Rows that
would normally be dropped for having a duplicate primary key are kept as well,
flagged in an added column.

`output/v3-temp` holds the data as it looked between steps, such as after
cleaning and before ID generation. Together these show the whole pipeline rather
than just its result.

Also open `output/v3-debug/logs/change_log_input.xlsx`, which the cleaning step
writes on every run. It records each correction made to the input, such as
enumeration values whose capitalization was fixed, and is the first place to
look when an output value is not what you expected.

## Where to go next

You have now run the Mapper end to end. From here:

- To convert a different format, the command is the same with a different
  `--module` — see [Supported Mappings](https://github.com/PHES-ODM/PHES-ODM-Mapper/blob/main/README.md#supported-mappings).
- To do something specific (map files that are not named after their tables, run
  from Python, build your own conversion), see the [How-to
  guides](../how-to/how_to.md).
- To understand what happened in Step 3 — why class names changed, where the IDs
  came from — read [How the Mapper Works](../explanation/explanation.md).
- For the full list of options, see the [Reference](../reference/reference.md).
