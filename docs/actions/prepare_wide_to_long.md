# Action: prepare_wide_to_long

Prepare wide-format data (eg. ODM v3 wide) for mapping to long format. The
action rewrites the wide columns into a universal, easily mapped intermediate
form, and **generates** the artifacts that the following steps need: the
LinkML-Map mapper schemas, a LinkML schema describing the prepared data, and the
ID code and linkage rules for creating the foreign keys in the long output.

## Where It Fits

`prepare_wide_to_long` is the first step of a wide-to-long module, and is
immediately followed by [`map`](map.md), which consumes the generated schema and
mappers. Later on, [`generate_ids`](generate_ids.md) consumes the generated ID
code and ID config. See [Wiring the Generated
Artifacts](#wiring-the-generated-artifacts) below.

All input DataFrames are concatenated into a **single** wide DataFrame
regardless of which class they were loaded as, so the input class names are
ignored. The action returns one class named `wide_data`.

## Example

The full wide-to-long sequence, as used by the `odm-v3-wide-to-long` module:

```yaml
- action: prepare_wide_to_long
  params:
    config: "wide_to_long/wide_to_long_odm_v3.yaml"
    target_schema: "{shared}/schemas/odm_v3.yaml"
    output_dir: "{temp}/wide_to_long/"
- action: map
  params:
    source_schema: "{temp}/wide_to_long/schema/schema.yaml"
    target_schema: "{shared}/schemas/odm_v3.yaml"
    mappers_dir: "{temp}/wide_to_long/"
```

## Parameters

| Parameter | Required/Optional | Description |
| :-------- | :---------------- | :---------- |
| `config` | Required | The configuration file for the wide-to-long preparation. Module-relative path; may start with `{shared}` or `{temp}`. See [Preparing the Config File](#preparing-the-config-file) below. |
| `target_schema` | Required | The LinkML schema for the target **long-format** dataset (eg. ODM v3 long). Module-relative path; may start with `{shared}` or `{temp}`. |
| `output_dir` | Required | Directory to write all generated artifacts to. This is an output path (not module-relative) and supports the `{output_dir}`, `{temp}`, `{debug_mode}`, and `{not_debug_mode}` variables. It is normally under `{temp}`. |

## Generated Artifacts

Everything below is written under `output_dir`:

| Path | Contents | Consumed by |
| :--- | :------- | :---------- |
| `*.yaml` (in the root) | The generated LinkML-Map mapper schemas, one per target class/group. | `mappers_dir` of the following [`map`](map.md) step |
| `schema/schema.yaml` | A generated LinkML schema describing the prepared (expanded) wide data returned by this action. | `source_schema` of the following [`map`](map.md) step |
| `ids/id_code.csv` | Generated ID code: the rules for generating the foreign keys that link the long tables. | one entry of `id_code` in [`generate_ids`](generate_ids.md) |
| `ids/id_code_config.yaml` | Generated ID config, containing the `class_linkages` that describe how the long tables link to each other. | one entry of `id_config` in [`generate_ids`](generate_ids.md) |
| `data/expanded.csv` | *(debug mode only)* The expanded wide data, for inspection. | — |
| `data/expanded_config.yaml` | *(debug mode only)* Metadata about the expanded data, such as which column groups were explicit in the input and which were generated. | — |

> **Warning:** when the mapper schemas are written, every existing `.yaml` and
> `.yml` file in the **root** of `output_dir` is deleted first (subdirectories are
> left alone). Point `output_dir` at a directory used only for these generated
> files — normally one under `{temp}` — and never at a directory holding
> hand-written module files.

Run with `--debug` and `--temp-dir` to keep and inspect these artifacts:

```console
odm-map --module odm-v3-wide-to-long --debug \
    --temp-dir "path/to/temp" \
    --output-dir "path/to/output" \
    "path/to/wide/input"
```

## Wiring the Generated Artifacts

The generated ID code and ID config must be added to the `generate_ids` step
**alongside** the module's regular ID files, because they only cover the foreign
keys implied by the wide columns. The `odm-v3-wide-to-long` module wires it up
like this:

```yaml
- action: generate_ids
  params:
    schema: "{shared}/schemas/odm_v3.yaml"
    id_code:
      - "{shared}/ids/general_v2_id_code.xlsx"
      - "{temp}/wide_to_long/ids/id_code.csv"
    id_config:
      - "{shared}/ids/general_v2_id_code.yaml"
      - "{temp}/wide_to_long/ids/id_code_config.yaml"
```

Order matters: when two ID code files provide code for the same class and slot,
the entry from the **later** file wins. Listing the generated file last
therefore lets it override the general rules where the wide-to-long linkage
requires it.

## Wide Column Names

The action reads the meaning of each wide column from its name. Column names are
made of parts separated by underscores, and the leading parts identify what kind
of column it is: an attribute (eg. `or_organizationID`), a measure (eg.
`wat_sa_liq_covN1_gch_me_1_value`), or a protocolSteps method or measure (eg.
`ps_met_pcrmeth_value`, `ps_mes_temp_cel_sin_1_value`). Columns whose type
cannot be determined are logged as warnings and ignored.

Expansion rewrites these into `tableShortName_attribute` columns, with a group
flag appended after a colon (eg. `mr_measure:g0`) when a single wide row
contains several measures or protocol steps that must not collide.

[wide_to_long_spec.md](../wide_to_long_spec.md) is the reference for the wide
column name format, including the `#_AND_` and `#_OR_` forms and how column
groups work. Read it before writing or debugging a wide-format input schema.

## Preparing the Config File

The config file is a YAML file with four top-level keys. The two that describe
the target data model — `tables_to_shortnames` and `partid_to_mmaset` — can be
generated from the ODM data dictionary (see [Generating the Config
File](#generating-the-config-file) below), while `see_headers` and
`custom_id_code` are hand-written.

The built-in example is
[/odm_map/data/modules/odm-v3-wide-to-long/wide_to_long/wide_to_long_odm_v3.yaml](/odm_map/data/modules/odm-v3-wide-to-long/wide_to_long/wide_to_long_odm_v3.yaml).

| Config key | Required/Optional | Description |
| :--------- | :---------------- | :---------- |
| `tables_to_shortnames` | Required | Maps each long-format table name to the short name used as the leading part of wide column names. |
| `partid_to_mmaset` | Optional | Maps a measure or method value to the enumeration ("mmaSet") that constrains the accompanying `value`. Needed to resolve `#_OR_` columns. |
| `see_headers` | Optional | Declares the "see other header" short codes, which let a wide column take its value from another column in the same row. |
| `custom_id_code` | Optional | Extra ID generation code appended to the generated `ids/id_code.csv`. |

### tables_to_shortnames

A dictionary mapping the **long table name** to its **short name**. The short
name is the leading part of every wide column belonging to that table, so this
key is what allows a column such as `mr_value` to be recognized as belonging to
`measures`.

```yaml
tables_to_shortnames:
  measures: mr
  measureSets: ms
  organizations: or
  protocolSteps: ps
  samples: sas
  sites: si
  # ...
```

Every table that can appear in the wide data must be listed. A column whose
leading part is not one of these short names cannot be identified as an
attribute column and is ignored with a warning.

### partid_to_mmaset

A dictionary mapping a measure or method value to the name of the enumeration
that its `value` must come from. These enumerations are called *mmaSets*
("measure, method, attribute sets") and are subsets of the broader methods and
measurements enumerations.

```yaml
partid_to_mmaset:
  pcrmeth: pcrSet
  seqStrat: seqStratSet
  extraction: extractSet
  influEqui: booleanSet
  # ...
```

This mapping is what resolves an `#_OR_` column, where a single value could
belong to one of several candidate measures or methods. For example, given the
column `ps_met_wat_sa_liq_2_OR_pcrmeth_seqStrat_value` with the value `amp`, the
action looks up the mmaSet for `pcrmeth` (`pcrSet`) and for `seqStrat`
(`seqStratSet`), finds `amp` in `seqStratSet`, and therefore writes `seqStrat`
into the `method` column and `amp` into the `value` column.

The set name cannot be derived by appending "Set" to the value — the enumeration
for `pcrmeth` is `pcrSet`, not `pcrmethSet` — which is why this explicit mapping
is required. If a mapped enumeration name does not exist in the target schema, a
warning is logged.

### see_headers

Some wide columns do not carry a value directly but say "see the value in
another header". Each entry gives the short code that appears in the column name
and the expanded column that the value should be read from:

```yaml
see_headers:
  aggregation:
    short_name: hAg
    slot: mr_aggregation
  compartment:
    short_name: hCo
    slot: mr_compartment
  fraction:
    short_name: hFr
    slot: mr_fraction
  measure:
    short_name: hMe
    slot: mr_measure
  specimen:
    short_name: hSp
    slot: mr_specimen
  unit:
    short_name: hUn
    slot: mr_unit
```

| Sub-key | Description |
| :------ | :---------- |
| `short_name` | The code that appears in place of a value in a wide column name (eg. `hUn` for "see the unit header"). |
| `slot` | The expanded column to read the value from (eg. `mr_unit`). |

The top-level key of each entry names the part of the column that the entry
applies to, so that a `hUn` appearing in the unit position resolves against the
unit header and not some other one. The recognized keys are `aggregation`,
`compartment`, `fraction`, `measure`, `specimen`, and `unit`; an entry under any
other key is never consulted. The `short_name` values, on the other hand, are
entirely up to you — they only need to match what appears in your wide column
names.

When resolving, the action first looks for the target column carrying the same
group flag as the column being resolved (eg. `mr_unit:g2` for a column in group
`g2`); if there is no such column it falls back to the ungrouped column
(`mr_unit`). If neither exists the value resolves to empty.

### custom_id_code

A list of extra ID code rows appended to the generated `ids/id_code.csv`. Use it
when a foreign key in the long output cannot be derived from the wide column
names alone. Each list item is one row, with `class`, `slot`, and one or more
`code` keys:

```yaml
custom_id_code:
- class: qualityReports
  slot: sampleID
  code000: |
    if dat.qualityReports.has_column("_extra_l_flag") and "l_sampleID" in str(dat.qualityReports._extra_l_flag).split(","):
        target = dat.measures.sampleID
    else:
        target = ""
```

| Sub-key | Description |
| :------ | :---------- |
| `class` | The long-format class the code populates. |
| `slot` | The slot within that class the code populates. |
| `code…` | Python code evaluated to produce the value. Any key beginning with `code` is a code column; they are renumbered into `code000`, `code001`, … in the order they appear, and are tried in that order until one produces a non-empty value. |

The code uses the same namespaces (`dat`, `datEmpty`, `fn`) as any hand-written
ID code — see [id_generator.md](../id_generator.md) for the full reference.

Custom rows are appended **after** the generated rows, and duplicates on
(`class`, `slot`) keep the last occurrence, so a custom entry overrides the
generated code for the same class and slot.

The example above also shows how link flags are used. The expander records a
column's `l_` flags in the `_extra_l_flag` column, so custom code can ask which
key a row should link to: a `qualityReports` row flagged `l_sampleID` takes its
`sampleID` from the linked `measures` row, and is left empty otherwise.

### Generating the Config File

`tables_to_shortnames` and `partid_to_mmaset` are derived from the ODM data
dictionary, so for ODM targets they should be generated rather than typed by
hand. Write a template holding the hand-maintained keys (`see_headers` and
`custom_id_code`), then run:

```console
python -m odm_map.prepare_wide_to_long.make_wide_to_long_config_cli \
    --data-dictionary "path/to/odm_data_dictionary.xlsx" \
    --config-template "path/to/template.yaml" \
    --output-file "wide_to_long/wide_to_long_odm_v3.yaml"
```

| Option | Description |
| :----- | :---------- |
| `--data-dictionary` | The Excel ODM data dictionary. The `parts` sheet is read and only rows whose `status` is `active` are used. |
| `--config-template` | A YAML file used as the starting point. Its keys are copied into the output, then `partid_to_mmaset` and `tables_to_shortnames` are added (overwriting those keys if the template already has them). |
| `--output-file` | Where to write the generated config. Parent directories are created as needed. |

The generated keys come from the data dictionary as follows:

- `partid_to_mmaset` — every `parts` row with a non-empty `mmaSet` whose
  `partType` is `methods` or `measurements`, mapping `partID` → `mmaSet`.
- `tables_to_shortnames` — every `parts` row whose `partType` is `tables`,
  mapping `partID` → `partInstr`.

Re-run this command whenever the data dictionary changes, and keep the template
under version control so the hand-written keys survive regeneration.

## Related Documentation

- [Pipeline Actions](README.md) — step structure, interpolation variables, and
  path resolution
- [wide_to_long_spec.md](../wide_to_long_spec.md) — the wide column name format
  and expansion rules
- [map](map.md) — the step that consumes the generated schema and mappers
- [generate_ids](generate_ids.md) — the step that consumes the generated ID code
  and ID config
- [id_generator.md](../id_generator.md) — reference for the code used in
  `custom_id_code`
- Implementation:
  [/odm_map/actions/action_prepare_wide_to_long.py](/odm_map/actions/action_prepare_wide_to_long.py),
  [/odm_map/prepare_wide_to_long/](/odm_map/prepare_wide_to_long/)
