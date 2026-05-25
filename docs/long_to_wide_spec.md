# Long-to-Wide Spec

This is the implementation spec for long-to-wide mapping. [Long-format,
wide-format, and wide-names](https://docs.phes-odm.org/wide-names.html) spec in
the ODM documentation. The goal is to map ODM long-format data into ODM wide-format data. The final section includes a list of steps required to implement this spec.

## Overview

Typically in a wide format each row represents a single date or a single sample, with each column representing a different variable or measurement performed on the same date or the same sample. In contrast, in a long format each row represents a single observation and multiple observations on the same date or sample are split up into different rows. Mapping from long to wide format can be tricky, as there are many ways in which the data can be represented in wide format.

## Types of wide columns

There are four types of wide columns we can create:

1. From the measures table, a single column that contains all the values in a single long-format row. This includes the following information (eg. `wat_si_NR_cod_mgL_m_1_value`):
   1. compartment
   2. specimen
   3. fraction
   4. measure
   5. unit
   6. aggregation
   7. index
   8. value
      
    The measure component can include an optional **OR aggregation**, where the measure can be one of multiple candidate values. In this case, the value in the row is a member of an enumeration set, and which enumeration set the value belongs to determines which of the measure values in the column name to use (eg. `wat_sa_liq_3_OR_otherM_otherA_otherV_gcMl_m_value`).
2. From the protocolSteps table, a single column that contains all the values for a single long-format row, where the protocol step is for a **measure** (eg. `ps_mes_temp_cel_sin_1_value`):
   1. measurement
   2. unit
   3. aggregation
   4. value
3. From the protocolSteps table, a single column that contains all the values for a single long-format row, where the protocol step is for a **method** (eg. `ps_met_seqStrat_value`):
   1. method
   2. value

    Similar to a measure in the measures table, the method can include an optional **OR aggregation**, where the method can be one of multiple candidate values. As before, the value in the row is a member of an enumeration set, and which enumeration set the value belongs to determines which of the method values in the column name to use (eg. `ps_met_2_OR_pcrmeth_seqStrat_value`)
4. An attribute that can be from any table. These contain both the table name and the column (eg. si_healthRegion). These can include an optional boolean **AND aggregation** for the column component, in which case the value found in the row is a dot-separated concatenation of two values, one for each column in the column name. In this case, the column name would be of the form `tableShortName_#_AND_column1_column2_..._column#` (eg. `or_2_AND_name_orgType`)

## Predefined Wide Columns

There are many ways that data in ODM long format can be represented in ODM wide
format. The same data, in wide format, can be represented by different column
names. It is likely that the user wants specific wide column names to be generated
in the mapping. This is especially useful for analysis purposes, where analysis
using specific columns will be performed downstream. As such, the user is given
the option to specify a list of wide column names to use. The mapper will then
use these columns as targets, and attempt to fill in other, non-specified wide
columns as best it can.

Below is an example configuration to specify which column names to generate:

```yaml
long_to_wide:
  predefined_wide_columns:
    - wat_si_NR_cod_mgL_m_1_value
    - ps_met_pcrmeth_value
    - or_2_AND_name_orgType
    - mr_sampleID
```

In this example, the mapper will attempt to generate the specified wide columns. If
data is available to fill in these columns, they will be filled in. If not, the
columns will be created but left empty. The mapper will also generate any other
wide columns it can, in addition to the specified ones.

## Grouping Rows

In the final wide format, each row represents a single sample or a single date. We need to group multiple long format rows by sample or date. This is fairly easy to accomplish using a configuration such as the following:

```yaml
long_to_wide:
  group_by:
    - sm_sampleID
```

In the above case, each sample will belong to a separate group. Within that group, values from other tables will be grouped with it. This grouping between tables is performed by foreign keys. Some foreign keys link **to** the samples table, while some foreign keys link **from** the samples tables.

As an example of linking **to** the samples table, the measures table has a `sampleID` as a foreign key to the samples table, so all measures with the same `sampleID` in the measures table will be grouped with that sample. In this case, there may be mutiple measures with the same `sampleID`, and so multiple rows from the measures table might be grouped together.

As an example of linking **from** the samples table, the samples table has a `protocolID` as a foreign key to the protocols table, so all protocols with the given `protocolID` will be grouped with the sample. Since `protocolID` is a primary key of the protocols table, only one row from the protocols table will be grouped.

Once the grouping and the target wide column names are specified, the mapper can proceed to fill in the wide columns for each group.

## Populating Pre-Specified Wide Columns

Once we have our group of rows, we can populate the pre-specified wide columns. These are the columns that were previously specified in the configuration.

### Attribute Columns

For attribute columns in the form tableShortName_attribute, we use the first value found in the group, from the source table and source column. For example, for the column `sm_sampleID` we will get the first value in our group that was obtained from the `samples` table under the column `sampleID`. We may want to log a warning or error if multiple values under this table/column are found, or if no values were found.

### Measures Columns

For wide columns for a measure, such as `wat_si_NR_cod_mgL_m_1_value`, we find the row obtained from the `measures` table that matches the components of the wide column name. In this case, we would look for a row in the `measures` table that matches the following values (obtained from the wide column name):

| compartment | specimen | fraction | measure | unit | aggregation | index |
|-------------|----------|----------|---------|------|-------------|-------|
| wat         | si       | NR       | cod     | mgL  | m           | 1     |

If such a row is found, we take the `value` from that row and populate the wide column with it. If no such row is found, we leave the wide column empty. We may want to log a warning or error if multiple rows match the criteria, or if no rows were found.

### Protocol Steps Method Columns

For wide columns for a protocol steps method, such as `ps_met_pcrmeth_value`, we perform the same matching as for a regular measure (see [Measures Columns](#measures-columns) above), but instead we look in the `protocolSteps` table for a row that matches the method component of the wide column name. In this case, we would look for a row in the `protocolSteps` table that matches the following values (obtained from the wide column name):

| method    |
|-----------|
| pcrmeth   |

If such a row is found, we take the `value` from that row and populate the wide column with it. If no such row is found, we leave the wide column empty. We may want to log a warning or error if multiple rows match the criteria, or if no rows were found.

### Protocol Steps Measure Columns

For wide columns for a protocol steps measure, such as `ps_mes_temp_cel_sin_value`, we perform the same matching as for a regular measure (see [Measures Columns](#measures-columns) above), but instead we look in the `protocolSteps` table for a row that matches the measurement component of the wide column name. In this case, we would look for a row in the `protocolSteps` table that matches the following values (obtained from the wide column name):

| measurement | unit | aggregation |
|-------------|------|-------------|
| temp        | cel  | sin         |

If such a row is found, we take the `value` from that row and populate the wide column with it. If no such row is found, we leave the wide column empty. We may want to log a warning or error if multiple rows match the criteria, or if no rows were found.

### Attribute Columns with AND Aggregation

Attribute columns with AND aggregation work similarly to a regular attribute columns, but instead of containing one value they contain two, separated by a dot. For example, for the column `or_2_AND_name_orgType`, we would look for two columns in the `organisms` table found in the group: `name` and `orgType`. We would then concatenate the two values found in these columns, separated by a dot, and populate the wide column with this concatenated value. We may want to log a warning or error if multiple values under either of these columns are found, or if no values were found.

### Measures Columns with OR Aggregation

A measure column can have an OR aggregation for the measure component. An example is `wat_sa_liq_2_OR_seqStrat_pcrmeth_gcMl_me_NR_value`. In this case, the `measure` can be `seqStrat` or `pcrmeth`. Which of these values to use for the measure depends on what is found in the `value` column in the row. If `seqStrat` is used, then `value` can take on any value from the enumeration `seqStratSet` (as defined in the ODM v3 LinkML schema). If `pcrmeth` is used, then `value` can take on any value from the enumeration `pcrSet`. We therefore need to find a row (in the group), where the `measure` is either `seqStrat` or `pcrmeth`, and where the `value` belongs to the corresponding enumeration set.

Below are two examples that would match:

| compartment | specimen | fraction | measure   | unit  | aggregation | index | value         |
|-------------|----------|----------|-----------|-------|-------------|-------|---------------|
| wat         | sa       | liq      | seqStrat  | gcMl  | me          | NR    | amp           |
| wat         | sa       | liq      | pcrmeth   | gcMl  | me          | NR    | qpcr          |

### Protocol Steps Method Columns with OR Aggregation

A protocol steps method column can also have an OR aggregation. An example is `ps_met_2_OR_pcrmeth_seqStrat_value`. In this case, the `method` can be `pcrmeth` or `seqStrat`. Which of these values to use for the method depends on what is found in the `value` column in the row. If `seqStrat` is used, then `value` can take on any value from the enumeration `seqStratSet` (as defined in the ODM v3 LinkML schema). If `pcrmeth` is used, then `value` can take on any value from the enumeration `pcrSet`. We therefore need to find a row (in the group), where the `method` is either `seqStrat` or `pcrmeth`, and where the `value` belongs to the corresponding enumeration set.

Below are two examples that would match:

| method      | value         |
|-------------|---------------|
| pcrmeth     | qpcr          |
| seqStrat    | amp           |

### Columns With See-Header Tags

Some wide columns may include a "see-header" tag in their name. This indicates that the value for this column is stored in a different column. For example, `hCo_hSp_NR_cod_mgL_m_1_value` has two see-header tags: `hCo` for the compartment and `hSp` for the specimen. These two parts can take on any value, rather than a fixed value such as with the previous header `wat_si_NR_cod_mgL_m_1_value` (where the compartment is fixed to `wat` and the specimen is fixed to `si`). The value for `hCo` and `hSp` are found in the columns `mr_compartment` and `mr_specimen`, respectively. Because these values can be anything, we do not need to match them when searching for the appropriate row in the group. Instead, we only need to match the other components of the wide column name. The following row will match `hCo_hSp_NR_cod_mgL_m_1_value` (where `*` means it can be any value):

| compartment | specimen | fraction | measure | unit | aggregation | index |
|-------------|----------|----------|---------|------|-------------|-------|
| *           | *        | NR       | cod     | mgL  | m           | 1     |

If such a row is found, we take the `value` from that row and populate the wide column with it. We will also populate two other columns: `mr_compartment` and `mr_specimen`, with the values found in the matching row for `compartment` and `specimen`, respectively.
If no such row is found, we leave the wide column empty. We may want to log a warning or error if multiple rows match the criteria, or if no rows were found.

### Repeating for all Groups

We repeat the population of pre-specified columns for all groups in our data. For each group, we keep track of which rows and columns within the group were used to populate the pre-specified columns. We will end up with groups containing unused rows and columns. We need to construct new wide column names that can be used to populate the remaining unused rows and columns in all the groups, until there are no unused rows/columns left. The difficult part is determining which wide column names to use, which is discussed next.

## Populating Un-Specified Wide Columns

Once all specified columns have been populated, we start populating the un-specified columns, which are determined programatically. The only tables that have specialized, more complex wide column names are the measures table and the protocolSteps table. For other tables, we can simply create wide column names based on the table and column names, as with the pre-specified attribute columns.

### Populating Wide Columns From Left-over Data

Given that we have populated the specified columns from various rows in our group, we now have incomplete rows that were used to populate the columns that still have data left over that were not copied over yet. For these left-over columns we simply use the `tableShortName_attribute` format, and give each of these new columns the same group as its corresponding row that was used to populate the specified columns.

### Populating Wide Columns From Non-Special Tables

As mentioned, only the protocolSteps and measures tables have specialized wide column names that contain values that originate from actual row data. Using the remaining unused protocolSteps ahd measures rows we need to decide on the best, most efficient wide column names to use.

