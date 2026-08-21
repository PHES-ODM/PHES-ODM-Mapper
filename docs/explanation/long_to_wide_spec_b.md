# Long-to-Wide Spec

This is the implementation spec for long-to-wide mapping. [Long-format,
wide-format, and wide-names](https://docs.phes-odm.org/wide-names.html) spec in
the ODM documentation. The goal is to map ODM long-format data into ODM wide-format data. The final section includes a list of steps required to implement this spec.

## Overview

Typically in a wide format each row represents a single date or a single sample, with each column representing a different variable or measurement performed on the same date or the same sample. In contrast, in a long format each row represents a single observation and multiple observations on the same date or sample are split up into different rows. Mapping from long to wide format can be tricky, as there are many ways in which the data can be represented in wide format.

## Types of wide columns

Based on the [PHES-ODM wide names specification](https://docs.phes-odm.org/wide-names.html), there are several types of wide columns:

### 1. Attribute Columns
**Formula:** `tableShortName_attribute`

**Example:** `sm_saMaterial` (sample material from the samples table)

**Components:**
- `tableShortName`: Short name of the source table (e.g., `sm` for samples, `si` for sites)
- `attribute`: Column name from that table

**Rules:**
- Uses snake_case naming convention
- Maps directly to a single column in a single table
- Takes the value as-is from the source column

### 2. Measure Columns
**Formula:** `compartment_specimen_fraction_measure_unit_aggregation_index_attribute`

**Example:** `wat_si_NR_cod_mgL_m_NR_value` (mean chemical oxygen demand from wastewater site measurements in mg/L)

**Components:**
1. `compartment`: Sample compartment (e.g., `wat` for wastewater, `air`, `sur` for surface)
2. `specimen`: Specimen type (e.g., `si` for site, `sa` for sample)
3. `fraction`: Sample fraction (e.g., `NR` for not reported, `liq` for liquid)
4. `measure`: The measurement being taken (e.g., `cod`, `temp`, `ph`)
5. `unit`: Unit of measurement (e.g., `mgL`, `cel`, `pH`)
6. `aggregation`: Aggregation method (e.g., `m` for mean, `sin` for single, `me` for median)
7. `index`: Index number (typically a number or `NR`)
8. `attribute`: Always one of `value`, `purpose`, or `qualityFlag`

**Rules:**
- All parts are required (use `NR` for "not reported" if not applicable)
- Values come from the measures table
- Must match all specified components to find the correct row

### 3. Protocol Steps Method Columns
**Formula:** `tableShortName_partTypeShortName_method_attribute`

**Example:** `ps_met_seqStrat_value` (sequencing strategy protocol step)

**Components:**
- `tableShortName`: Always `ps` for protocolSteps
- `partTypeShortName`: Always `met` for method
- `method`: The method being used (e.g., `seqStrat`, `pcrmeth`)
- `attribute`: Typically `value`, `purpose`, or `qualityFlag`

**Rules:**
- Maps to rows in protocolSteps table where the part type is method
- Method value must match exactly

### 4. Protocol Steps Measure Columns
**Formula:** `tableShortName_partTypeShortName_measure_unit_aggregation_index_attribute`

**Example:** `ps_mes_temp_cel_sin_NR_value` (storage temperature measurement)

**Components:**
- `tableShortName`: Always `ps` for protocolSteps
- `partTypeShortName`: Always `mes` for measure
- `measure`: The measurement (e.g., `temp`)
- `unit`: Unit of measurement (e.g., `cel`)
- `aggregation`: Aggregation method (e.g., `sin`)
- `index`: Index number or `NR`
- `attribute`: Typically `value`

**Rules:**
- Maps to rows in protocolSteps table where the part type is measure
- Must match measure, unit, and aggregation

### 5. Combined Attribute Columns (AND Aggregation)
**Formula:** `tableShortName_n_aggregation_attribute1_..._attributeN`

**Example:** `sm_2_AND_collPer_collNum` (collection period and number combined)

**Components:**
- `tableShortName`: Short name of the source table
- `n`: Number of attributes being combined
- `aggregation`: Always `AND` for attributes
- `attribute1...attributeN`: List of column names to combine

**Rules:**
- Combines multiple columns from the same table
- Values are concatenated with period separator (`.`)
- Example output: "24.12" (period 24, collection number 12)

### 6. Combined Measure Columns (OR Aggregation)
**Formula:** `compartment_specimen_fraction_n_aggregation_measure1_..._measureN_unit_aggregation_index_attribute`

**Example:** `wat_sa_liq_3_OR_otherM_otherA_otherV_gcMl_m_value` (variant measurements)

**Components:**
- Standard measure components (compartment, specimen, fraction, unit, aggregation, index, attribute)
- `n`: Number of measures that can match
- `aggregation`: Always `OR` for alternative measures
- `measure1...measureN`: List of possible measure values

**Rules:**
- All measures must share identical units and aggregation values
- The actual measure used depends on which enumeration set the value belongs to
- Only one measure will match per row based on the value's enumeration

### 7. Combined Method Columns (OR Aggregation)
**Formula:** `tableShortName_partTypeShortName_n_aggregation_method1_..._methodN_attribute`

**Example:** `ps_met_2_OR_pcrmeth_seqStrat_value` (PCR or sequencing selection)

**Components:**
- `tableShortName`: Always `ps`
- `partTypeShortName`: Always `met`
- `n`: Number of methods that can match
- `aggregation`: Always `OR`
- `method1...methodN`: List of possible method values
- `attribute`: Typically `value`

**Rules:**
- The actual method used depends on which enumeration set the value belongs to
- Only one method will match per row based on the value's enumeration

### 8. See-Header (Mixed Format) Columns
**Formula:** Uses `h` prefix tags like `hFr`, `hMr`, `hUn`, `hAg`, `hCo`, `hSp`

**Example:** `wat_sa_hFr_hMr_hUn_hAg_NR_value` (measure with variable fraction, measure, unit, and aggregation)

**Components:**
- Standard position components with `h`-prefixed wildcards:
  - `hCo`: Variable compartment (value in separate `mr_compartment` column)
  - `hSp`: Variable specimen (value in separate `mr_specimen` column)
  - `hFr`: Variable fraction (value in separate `mr_fraction` column)
  - `hMr`: Variable measure (value in separate `mr_measure` column)
  - `hUn`: Variable unit (value in separate `mr_unit` column)
  - `hAg`: Variable aggregation (value in separate `mr_aggregation` column)

**Rules:**
- Used for combined long/wide-format tables
- See-header parts indicate metadata specified in other columns
- When matching rows, see-header parts match any value
- The actual values are stored in separate `mr_*` columns (e.g., `mr_compartment`, `mr_specimen`)
- These columns must be populated alongside the value column

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

## Populating Remaining Columns

Once all the pre-specified columns have been populated, we need to populate other wide columns so that all the source data from the long-format dataset is represented in the wide-format dataset. There are many possible additional wide column names that can result from this. The goal is to ensure that all source data gets copied over to the wide format.

