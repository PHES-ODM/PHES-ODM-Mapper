# How the Mapper Works

This document explains the ideas behind the Mapper: what a module is, what the
pipeline does to your data, and why the output looks the way it does. It is
background reading rather than instructions — for the commands, see the
[tutorial](tutorial.md) and the [how-to guides](how_to.md); for exact
parameters, see [reference.md](reference.md).

- [The problem being solved](#the-problem-being-solved)
- [Modules](#modules)
- [LinkML and LinkML-Map](#linkml-and-linkml-map)
- [The pipeline](#the-pipeline)
- [How data flows between steps](#how-data-flows-between-steps)
- [Cleaning before and after mapping](#cleaning-before-and-after-mapping)
- [Why rows are filtered out](#why-rows-are-filtered-out)
- [Why IDs have to be generated](#why-ids-have-to-be-generated)
- [Internal columns](#internal-columns)
- [The `_shared` module](#the-_shared-module)
- [Wide and long formats](#wide-and-long-formats)
- [Performance](#performance)

## The problem being solved

Wastewater surveillance data is reported in a number of formats — ODM v1, NWSS
Reporting, PHA4GE — that differ from the PHES-ODM not only in the names of their
columns but in their shape. A single NWSS row can carry many measurements that
the ODM represents as many rows across several tables. Values are drawn from
different vocabularies. And the ODM's tables are linked by primary and foreign
keys that the source data usually does not contain at all.

A conversion is therefore more than a column-renaming exercise. It has to
restructure rows, translate vocabularies, and invent a consistent set of keys
that make the resulting tables refer to one another correctly. The Mapper exists
to do all of that in one pass, and to make each part of it something you can
configure rather than something you have to program.

## Modules

Everything specific to one conversion lives in a **module**: a directory holding
a `config.yaml` and the files it refers to — LinkML schemas, LinkML-Map mapping
files, filter rules, ID-generation code. The Mapper's Python code contains no
knowledge of ODM v1, NWSS, or PHA4GE; it only knows how to execute the actions a
module asks for.

This is why supporting a new format does not require changing the Mapper. A
module is data, so it can be written by someone who knows the source format
rather than the codebase, kept outside this repository, and distributed as a ZIP
file. The four built-in modules are ordinary modules that happen to ship with
the package.

## LinkML and LinkML-Map

The formats themselves are described in [LinkML](https://linkml.io) schemas. A
schema names the tables of a format, the slots (columns) of each table, the
enumerations a slot's values may be drawn from, and the patterns those values
must match. Both the source and target formats of a conversion have one.

Having a machine-readable description of both ends is what allows so much of the
work to be generic. The Mapper uses the source schema to recognize which table
an input file belongs to, to correct the capitalization of enumeration values,
and to report values that fail a pattern check. It uses the target schema to do
the same on the way out and to know which columns belong in the final output.

The transformation between the two is expressed in
[LinkML-Map](https://github.com/linkml/linkml-map) files, which describe how
each target slot is derived from source slots. The [`map`](actions/map.md) action
runs them.

## The pipeline

A module's `steps` are an ordered list, each running one **action**. The actions
available are:

| Action | Purpose |
| :----- | :------ |
| [`clean`](actions/clean.md) | Normalize column names, correct enumeration values, check patterns |
| [`select_enum_hierarchy`](actions/select_enum_hierarchy.md) | Drop enum values made redundant by a more specific value in the same cell |
| [`map`](actions/map.md) | Transform source tables into target tables |
| [`prepare_wide_to_long`](actions/prepare_wide_to_long.md) | Restructure wide data and generate what is needed to map it |
| [`expand`](actions/expand.md) | Split multivalued cells into one row each |
| [`filter`](actions/filter.md) | Remove rows that should not be in the output |
| [`generate_ids`](actions/generate_ids.md) | Create primary and foreign keys |
| [`drop_columns`](actions/drop_columns.md) | Remove internal and non-schema columns |
| [`save`](actions/save.md) | Write the data to CSV files |

Steps are free-form: an action can appear as many times as it is useful, and a
step can be made conditional on debug mode with the `if` key. What the built-in
modules have in common is a shape rather than an exact sequence — clean the
input, map it, tidy the result, generate keys, save — and modules differ in
which of the optional steps they need. [A typical pipeline
order](actions/README.md#a-typical-pipeline-order) sets out that shape in full.

Because the steps are configuration, a module author can insert a debug-only
[`save`](actions/save.md) anywhere to see the data at that point, which is the
main reason `--debug` and `--temp-dir` are so useful when something goes wrong.

## How data flows between steps

Every action receives the data as a dictionary of class (table) name to a list
of DataFrames, and returns the same structure. The output of one step is the
input to the next. Two consequences matter when reading or writing a module:

**The class names change at `map`.** Before it, they are the source format's
tables (`WWMeasure` in ODM v1); after it, they are the target's (`measures` in
ODM v3). Any action taking a `schema` parameter must be given whichever schema
matches the data at that point, which is why modules pass the source schema to
the first `clean` and the target schema to the second.

**A class can hold several DataFrames.** If three files were loaded into the
same table, they stay separate until an action merges them —
[`filter`](actions/filter.md) and [`save`](actions/save.md) concatenate them
before doing their work.

## Cleaning before and after mapping

Cleaning happens twice in most modules, for different reasons.

Before mapping, the input is normalized so that the mapping rules can rely on
it: column names are matched to schema slot names despite differences in case,
punctuation, and spacing, and enumeration values are corrected to the exact form
the schema defines. Real input data varies in ways that are not worth encoding
into every mapping rule.

After mapping, the output is cleaned against the *target* schema, because a
transformation can produce a value that is correct in substance but not in the
form the target format specifies.

Every correction is recorded in the change log written by the `clean` step. When
an output value is not what you expected, that log usually says why.

## Why rows are filtered out

Mapping is applied uniformly to every source row, so it can produce rows that
should not exist in the output: rows where a required value came out blank,
placeholder rows, rows carrying sentinel values that mean "no data". Filtering
removes them after mapping rather than before, since whether a row is empty is
often only visible in target terms.

Modules commonly filter twice: once after mapping, and once after ID generation
when a row's required values are finally known. The rules live in a filter file,
described in [filters.md](filters.md).

## Why IDs have to be generated

The ODM links its tables with primary and foreign keys — a measure points at the
sample it was taken from, a sample points at its site. Source formats generally
do not carry these keys. A single NWSS row becomes rows in several ODM tables
that must end up pointing at each other, and there is nothing in the input that
says so.

The Mapper solves this with the tracking columns added during mapping. Every
output row remembers the source file and row it was built from, so rows derived
from the same source row can be recognized as belonging together, and keys can
be generated that link them. Key values themselves are produced by small pieces
of code in the module's ID code file, which is what allows a module to control
their format. The mechanism is described in
[id_generator.md](id_generator.md).

This is also the most expensive part of a large run, since it requires comparing
rows across tables.

## Internal columns

Two families of columns exist only inside the pipeline:

- **Tracking columns** record where each row came from: `(__source_file__)`,
  `(__source_class__)`, `(__source_row__)`, and `(__source_file_and_row__)` —
  in general, any column starting with `(__` and ending with `__)`. ID
  generation depends on them.
- **Extra columns** carry temporary non-schema data needed during processing,
  such as tags used for linking. They start with `_extra_`.

Modules that include a [`drop_columns`](actions/drop_columns.md) step remove
them before the final save, usually only when not running in debug mode; modules
without one leave them in the output. Seeing them in a result is normal, not a
sign that something went wrong.

## The `_shared` module

Some files are needed by several conversions — the ODM schemas, the general ID
code, filters for required values. Rather than copying them into each module,
they live in the `_shared` module at
[/odm_map/data/modules/_shared](/odm_map/data/modules/_shared), and modules
refer to them with the `{shared}` path prefix. A fix to the ODM v3 schema then
reaches every module that maps to ODM v3.

## Wide and long formats

The ODM's normal, long form puts one measurement per row. Data is often
collected in a wide form instead, with one row per sample and a column per
measurement, where the column names encode which measure, unit, and compartment
each value belongs to.

Converting between the two is not a fixed mapping, because the set of columns
differs from dataset to dataset — the mapping rules depend on the data being
mapped. This is why the wide-to-long module has an extra
[`prepare_wide_to_long`](actions/prepare_wide_to_long.md) step: it reads the
wide column names, restructures the data, and *generates* the mapping files,
schema, and ID code that the subsequent `map` and `generate_ids` steps then use
in the ordinary way. The column naming scheme it reads is specified in
[wide_to_long_spec.md](wide_to_long_spec.md).

## Performance

Mapping cost grows with the output, not the input. Because one source row can
become many target rows, a modest input can produce a very large result: an NWSS
dataset of 650,000 rows can map to over 30,000,000 ODM rows, which can take 15
hours or more even on a fast machine. Smaller datasets finish in minutes.

The two expensive stages are the initial mapping, which applies the
transformation to every row, and ID generation, which has to relate rows across
tables. Mapping parallelizes across processes (`--max-processes`); large runs
also need a substantial amount of RAM and benefit from fast storage for the
temporary directory. [Speed up a large
mapping](how_to.md#speed-up-a-large-mapping) covers what to do in practice.
