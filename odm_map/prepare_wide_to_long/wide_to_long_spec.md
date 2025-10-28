# Wide-Long Spec

This is the implementation spec for ODM wide-to-long mapping. It follows the
[Long-format, wide-format, and
wide-names](https://docs.phes-odm.org/wide-names.html) spec in the ODM
documentation. The final section provides a list of steps to perform for
developing wide-to-long functionality.

## Terminology

A column name consists of parts separated by underscores. For example, the
column name `ps_met_seqStrat_value` has four parts, named `ps`, `met`,
`seqStart`, and `value`.

## Parsing Column Names

To identify what type of column we have, given a column name, we use the
following rules:

- If the column name starts with a tableShortName, such as `ps` (protocol
  steps), `sm` (samples), `co` (for contacts), and the second part is not `mes`
  or `met`, then it’s an attribute. eg: `co_contactID`
  - If the second part is preceded by `#_AND_` then it is multiple
    dot-separated values for multiple attributes. eg:
    `sm_2_AND_collPer_collNum` (an example value would be `24.12`)
  - If the second part is preceded by `#_OR_` then it is a single value for a
    single attribute. The attribute that the value belongs to is determined by
    either the type of the value (eg. a string vs a float) or by which
    enumeration the categorical value belongs to. eg:
    `sm_2_OR_unit_aggregation`. If the value is `gcMl`, then the value is
    placed in the `unit` column because it belongs to the `units` enumeration.
    If the value is `me`, then the value is placed in the `aggregation` column
    because it belongs to the `aggregations` enumeration.
- If the column name starts with the tableShortName `ps`, and the second part
  is either `mes` or `met`, then it’s a protocol step where we parse the name
  as tableShortName_partTypeShortName_method_attribute (for a method) or
  `tableShortName_partTypeShortName_measure_unit_aggregation_index_attribute`
  (for a measure). eg: `ps_met_seqStrat_value` (method),
  `ps_mes_temp_cel_sin_NR_value` (measure)
  - If the method (3rd part) is preceded by `#_OR_` then it is a single value.
    The value for the `method` column is determined by identifying which
    enumeration the value belongs to. For example, if the column is
    `ps_met_wat_sa_liq_2_OR_pcrmeth_seqStrat_value` and the value in that
    column is `amp`, then because `amp` belongs to the enumeration
    `seqStratSet` (and not `pcrSet`), the `method` column will receive the
    value `seqStrat` and the `value` column will receive the value `amp`.
  - **TODO: How to figure out which enumeration pcrmeth and seqStart use? We
    cannot just append the string "Set", since the enumeration for pcrmeth is
    "pcrSet", not "pcrmethSet"**
- If the column name does not start with a recognized tableShortName, then it’s
  a measure in the form
  `compartment_specimen_fraction_measure_unit_aggregation_index_attribute`. eg:
  `wat_si_NR_cod_mgL_m_NR_value`
  - If the measure (4th part) is preceded by `#_OR_` then it is a single value.
    The value for the `measure` column is determined by identifying which
    enumeration the value belongs to. For example,
    `wat_sa_liq_3_OR_otherM_otherA_otherV_gcMl_m_value` will contain a value
    that either belongs to the enumerartions for `otherM`, `otherA`, or
    `otherV`. If the value `b11` belongs to the enumeration for `otherV`, then
    the `measure` column will receive the value `otherV`, and the `value`
    column would receive the value `b11`.
  - **TODO: How to figure out which enumeration otherM, otherA, and otherV
    use?**

## Expanding Column Names

Once the type of column is identified, the column should be expanded for each
row in the table. The new column names in the expansion will be preceded by the
target table name (eg. `mr`)

### Example Measure Expansion

A measure wide column is in the form
`compartment_specimen_fraction_measure_unit_aggregation_index_attribute`. Below
is an example of a single wide column that is a measure.

| wat_sa_liq_covN1_gch_me_1_value |
|---------------------------------|
| 100                             |
| 120                             |

The above gets expanded into multiple `tableShortName_attribute` columns, all
belonging to the measures table:

| mr_compartment | mr_specimen | mr_fraction | mr_measure | mr_unit | mr_aggregation | mr_index | mr_value |
|----------------|-------------|-------------|------------|---------|----------------|----------|----------|
| wat            | sa          | liq         | covN1      | gch     | me             | 1        | 100      |
| wat            | sa          | liq         | covN1      | gch     | me             | 1        | 120      |

### Example Attribute Expansion

Attribute expansion is fairly simple, as it is already in the
`tableShortName_attribute` format and so no expansion is required. The
exception is when `#_AND_` is included in the column name, as described below.

### Example protocolSteps Expansion

Both protocolSteps methods and measures wide columns get expanded into multiple
protocolSteps columns. protocolSteps columns can include `#_AND` and `#_OR`
values which make expansion slightly more complicated. These exceptions are
described in a later section, with the basic protocolSteps expansion described
here. The table below shows an example protocolSteps methods wide column for
the `value` attribute:

| ps_met_pcrmeth_value |
|----------------------|
| amp                  |

The above gets expanded to:

| ps_method | ps_value |
|-----------|----------|
| pcrmeth   | amp      |

Below is an example protocolSteps measure wide column for the `value`
attribute:

| ps_mes_temp_cel_sin_1_value |
|-----------------------------|
| 20                          |

The above gets expanded to:

| ps_measure | ps_unit | ps_aggregation | ps_index | ps_value |
|------------|---------|----------------|----------|----------|
| temp       | cel     | sin            | 1        | 20       |

### Groups for Column Names

Within a single wide row, it's possible that we may have multiple measures or
multiple protocolSteps. The table below shows an example of two measures in a
single wide row, one for the measure `covN1` and another for the measure
`pcrmeth`:

| wat_sa_liq_covN1_gcL_me_1_value | wat_sa_liq_pcrmeth_gcMl_me_NR_value |
|---------------------------------|-------------------------------------|
| 40                              | amp                                 |

When expanding these columns, we want to make sure there are no duplicate
column names in the `tableShortName_attribute` format. To avoid these
conflicts, we add a group after each expanded column name in order to group the
columns and make their names unique. The group can be any string that starts
with the letter "o", but we will use the zero-based column index in the source
wide row that the target column was expanded from, preceded by the letter "o"
and a colon (ie. ":o#"). Using this method, the columns for `covN1` will
receive the group `:o0` and the columns for `pcrmeth` will receive the group
`:o1` (the following table has been split in two for readability reasons, but
should be interpreted as a single table with a single row):

| mr_compartment:o0 | mr_specimen:o0 | mr_fraction:o0 | mr_measure:o0 | mr_unit:o0 | mr_aggregation:o0 | mr_index:o0 | mr_value:o0 |
|-------------------|----------------|----------------|---------------|------------|-------------------|-------------|-------------|
| wat               | sa             | liq            | covN1         | gcL        | me                | 1           | 40          |

| mr_compartment:o1 | mr_specimen:o1 | mr_fraction:o1 | mr_measure:o1 | mr_unit:o1 | mr_aggregation:o1 | mr_index:o1 | mr_value:o1 |
|-------------------|----------------|----------------|---------------|------------|-------------------|-------------|-------------|
| wat               | sa             | liq            | pcrmeth       | gcMl       | me                | None        | amp         |

We will automatically add these groups whenever expanding a measure wide
column, a protocolSteps measure wide column, a protocolSteps method wide
column, or any attribute column that has an `AND` boolean aggregator, such as
`in_2_AND_name_insType`.

### Example Handling for `#_AND_` in Column Names

If `#_AND_` is found in the column name for an attribute, then the value
contains multiple dot-separated values. For example, given the following table:

| sm_2_AND_collPer_collNum |
|--------------------------|
| 24.12                    |

We would expand it to:

| sm_collPer | sm_collNum |
|------------|------------|
| 24         | 12         |

### Example Handling for `#_OR_` in Column Names

If `#_OR_` is found in the column name, then there is a single value in that
row, but we need to determine which enumeration that value belongs to. For
example, given the following table:

| wat_sa_liq_3_OR_otherM_otherA_otherV_gcMl_me_NR_value |
|-------------------------------------------------------|
| b11                                                   |

If the value `b11` belongs to the enumeration for `otherV`, then the `measure`
column receives the value `otherV` and the `value` column reeives the value
`b11`:

| mr_compartment | mr_specimen | mr_fraction | mr_measure | mr_unit | mr_aggregation | mr_index | mr_value |
|----------------|-------------|-------------|------------|---------|----------------|----------|----------|
| wat            | sa          | liq         | otherV     | gcMl    | me             |          | b11      |

Because all enumerations are mutually exclusive, `b11` is guaranteed to only
belong to one of the enumerations `otherM`, `otherA`, and `otherV`.

### Handling Duplicate Columns When Expanding

***This section needs updating or removal. It has overlap with the columns with
indices section above.***

At the moment there is no finalized spec on how to deal with cases where we may
get two different values for the same column. For example, if we have two
organizations in a single wide row, we would need two columns for
`or_organizationID`. This would correspond to a case where, when mapping from
wide to long, we would have two rows in the final long organizations table,
rather than just one. For the moment, if we have multiple columns with the same
name in the wide table, we will append an underscore and an index after the
column name, as below:

| or_organizationID | or_organizationID_2 |
|-------------------|---------------------|
| OHRI              | ABCD                |

Columns that have the same index will map onto the same row when mapping from
wide to long.

## Mapping From Wide to Long

Once we have expanded all the data in the wide table, we can start the mapping
process. This will require programatically creating the LinkML-Map mapping
schemas for each ODM long format table.

We iterate over all columns in the expanded wide table. We read the leading
table short name identifier (eg. `mr_compartment` has the table short name `mr`
which is for the measures table). For that given table, we will add a mapping
rule from the source column (eg. `mr_compartment`) to the target column (eg.
`compartment`). The target table and target column are both read from the
source column name. If the source column name has an index (eg.
`mr_compartment_2`) we modify the LinkML-Map schema for that specific index
(eg. index 2 for `mr_compartment_2`).

Once all mapping schemas are complete, we can pass these schemas onto the
Mapper pipeline.

## Development Steps

The following are the steps required to implement wide to long mapping, in the
suggested order:

1. Expand column names: Take all columns that have a recognizable wide-name
   format and expand them into a separate table. All columns in the new table
   have a name in the format tableShortName_column. Optionally, an index is
   added to the end of the column if there is multiple values for that column,
   ie. in the format tableShortName_column_#. This would be a single action in
   the pipeline, called `expand_wide_slots`.
2. Create LinkML-Map mappers to map the new expanded data to long format. This
   should also deal with the optional indices added to the end of the column
   names, for when there are multiple values for a column. Whenever a foreign
   key is specified (eg. mr_organizationID), a row with that ID should be
   created in the table that that key points to. This would be a single action
   in the pipeline, called `create_wide_to_long_mappers`.
3. Create a full pipeline and test the results.