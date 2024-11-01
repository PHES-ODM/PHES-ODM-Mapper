# ID Generator

## Introduction

After the initial mapping step with the LinkML-Map schemas and the filtering step to remove unwanted rows, IDs can be generated for all rows in the output tables. These IDs can act as primary and foreign keys, and it can be ensured that primary keys are all unique. Because ID generation is performed after mapping it is possible to use the final values in the output to construct the IDs by combining various values in the rows. When set up properly we can link rows between the various tables using the generated IDs.

Generating IDs is fairly flexible and can be expressed as short Python code segments specified in configuration files. It is also possible to generate non-ID values, such as formatting dates and times correctly.

There are two configuration files that must be created:

1. *General Configuration File*: Specifies some general settings, such as which slot is the primary key for each class.
2. *Code Configuration File*: Species the Python code that is executed to generate the IDs or values of the various slots.

The location of these files within a conversion module are specified in the module configuration file ([Custom Modules](custom_modules.md)). See below for details of both files.

## General Configuration File

This is a simple YAML file that specifies some general configuration. At the moment the only setting is `primary_keys`, which is a dictionary where the keys are class names and the values are the single primary key for that class. See below for an example:

```yaml
primary_keys:
  addresses: addressID
  contacts: contactID
  datasets: datasetID
  # ...
```

## Code Configuration File

The code configuration file specifies the Python code to generate IDs can be stored in either a CSV file or an Excel file. The following columns should be included:

1. *class*: The class that the current configuration row is for.
2. *slot*: The slot that the current configuration row is for.
3. *code*: The Python code that is executed to generate the ID for the slot. Any column that starts with the word *code* will be considered a code column. (eg. "code1", "codeb", etc.). After executing the code, the resulting value from code execution will be used. Or if the variable "target" is set by the code, then that value is used instead.

For all the mapped data, we generate values according to the configuration, and populate the specified `slot` within each specified `class`. The code from each *code* column will be executed starting with the left-most *code* column, working rightward. If the code for a column generates a non-empty value (or sets the variable "target" to a non-empty value), that value is used as the ID for the slot. If an empty value is generated, then the next *code* column is executed. This is repeated until a non-empty value is generated or the last code column is executed.

An example configuration table is shown below:

| class     | slot      | code0                     | code1 |
|:----------|:----------|:--------------------------|:------|
| addresses | addressID | dat.addresses.__addressID | fn.makeid(datEmpty.addresses.country, datEmpty.addresses.pCode, datEmpty.addresses.city[:3]) |
| addresses | datasetID | dat.datasets.datasetID    |       |
| measures  | siteID    | dat.measures.__siteID     | <pre style="padding: 0; margin: 0; font-size:90%">if fn.sourceclass == "WWMeasure":<br>    target = dat.samples.get_first_linked_value(<br>                   "siteID",<br>                   linkage_path={"source_slot":"sampleID", "target_slot":"sampleID"}<br>                   )<br>else:<br>    target = ""</pre> |

With the above example, we will iterate over all rows of the table `addresses`, generating the ID for `addressID` and `datasetID` according to the code in `code0` and `code1`. In the documentation below, we will say that the current class is `addresses` and the current row is the zero-based row number being generated within the `addresses` table. Continuing with the above example, we will also iterate over all rows in `measures` and generate the ID for `siteID` according to the code in `code0` and `code1`.

## Linking Between Tables

There are many cases where linking between rows in different output tables is required. For example, a row in the `measures` table, where a value is recorded (eg. quantity of covN1), would need a `sampleID` to associate it with a specific sample. These `sampleID`s may have been generated in the `samples` table, and we need to know which `sampleID` in particular to use in our row in the `measures` table. This pairing of rows is called linking. Once rows are linked between tables, we can extract other associated data from the linked rows, such as the sample's collection date and time.

In the simplest case, we might have mapped a single source table such as NWSS to multiple target tables corresponding to the multiple tables found in ODM v2. In order to determine which `sampleID` to use, we simply need to identify which row in NWSS was used to populate the current row in `measures` and identify which row in `samples` was populated from the same NWSS row. This will give us our linked row which we can extract the `sampleID` from. We can also extract other values from the linked row, such as `collDT` for the collection date and time of the sample. The source row from NWSS that populated the target row is temporarily stored in the mapped tables for linking purposes (eg. see [fn.sourceclass](#fnsourceclass) and [fn.sourcerow](#fnsourcerow) below).

By default, linking is performed by matching the source class and row number. However, this doesn't always work, especially if the source database has multiple tables such as with ODM v1. We can link by matching any column between rows (often we match a foreign key in one table with a primary key in another table, but the matching does not have to involve key values). We can also link via multiple tables, for example, from the source `measures` table, we can link to the `samples` table by matching the `sampleID` column, then from the `samples` table we can link to the `organizations` table by matching the `organizationID`. To specify this custom linking, one can use a function such as `fn.get_first_linked_value()` (see below).

## Code Namespaces

There are several namespaces that can be used in the ID generation code:

1. dat and datEmpty
2. fn

### dat and datEmpty Namespaces

The *dat* and *datEmpty* namespaces provide access to all the target database tables and slots. Accessing these namespaces will return values from linked rows. The format is `dat.className.slotName`, for example, `dat.samples.sampleID` will return the `sampleID` of the linked row in the `samples` table. Linking is performed by matching the class and row number in the source database used to populate the current row. If linking via different slots or tables is required, use `get_first_linked_value` (see below for details).

If a slot is accessed using either `dat` or `datEmpty` (including accessing intermediary slots used for linking between rows), and the slot is configured to have a generated ID according to the ID config file, then the value of that slot will be calculated before returning the value.

If `dat` is used to access a value, then the value will be returned. If `datEmpty` is used, then the value will also be returned, but if the value is blank or does not exist, then the string "empty" will be returned. The `datEmpty` namespace is useful when creating IDs with the `fn.makeid()` function, in which we would like the different parts of the ID to be non-empty.

In order to access the value that a slot had BEFORE it was generated, precede the slot name with two underscores (`__`). For example, if `sampleID` in table `samples` is generated through the ID config file, then `dat.samples.sampleID` will return the generated ID, whereas `dat.samples.__sampleID` will return the original `sampleID` before it was generated (ie. what `sampleID` was initially populated with).

#### dat.targetClass.get_first_linked_value(target_slot, linkage_path=None)

Extract the value in `target_slot` for the first linked row in the target table. The following two operations are equivalent and will extract the `sampleID` for the linked row in the target table `samples`:

```python
dat.samples.get_first_linked_value("sampleID")
dat.samples.sampleID
```

If `linkage_path` is None, then linking is performed by matching the source database table and row used to populate the current row being generated.

`linkage_path` can also be a dictionary of the form:

```python
linkage_path = {
    "source_slot" : "sourceSlotName",
    "target_slot" : "targetSlotName",
}
```

The above linkage path would extract the linked row in the target table (ie. the table named `tableName` when calling `dat.tableName.get_first_linked_value()`) where the value in `targetSlotName` is equal to the value in `sourceSlotName` of the current row.

It is also possible to link via multiple tables using an array of linkage paths:

```python
linkage_path = [
    {
        "source_class": "class_a",
        "source_slot": "slot_a",
        "target_class": "class_b",
        "target_slot": "slot_b"
    },
    {
        "source_class": "class_b",
        "source_slot": "slot_b2",
        "target_class": "class_c",
        "target_slot": "slot_c"
    },
    {
        "source_class": "class_c",
        "source_slot": "slot_c2",
        "target_class": "class_d",
        "target_slot": "slot_d"
    },
]
```

In the above example, we first link to table `class_b` by matching the value in `slot_a` of the current row with values in `slot_b` of the target table. Once the linked row is found, we use that new row to link to table `class_c` by matching the value in `slot_b2` of the new current row with values in `slot_c` of the target table `class_c`. Once the linked row is found, we repeat the step to get the final linked value in slot `slot_d` of table `class_d`.

Note that `source_class` can be excluded from the first dictionary, as it is already implied by the current class that IDs are being generated for (ie. the `class` column in the ID config file that the code belongs to). `source_class` can also be excluded in any of the other dictionaries as it is implied by the `target_class` of the previous dictionary. Finally, `target_class` can be omitted from the final dictionary as it is implied in the call to `dat.targetClass.get_first_linked_value()`.

### fn Namespace

The *fn* namespace provides various functions and attributes commonly used in ID generation code.

#### fn.makeid(*args)

Concatenate all arguments into a single string with spaces removed. The first character of args[0] is lowercased, while the first character of all other args are uppercased. Typically, each argument is usually a result of accessing values through `datEmpty`. For example:

```python
fn.makeid(datEmpty.addresses.country, datEmpty.addresses.pCode, datEmpty.addresses.city[:3])
```

If an ID is passed as an argument to `fn.makeid` (eg. `datEmpty.sites.siteID`), then the ID's index will be removed. The ID's index is an extra number added to the end of an ID to differentiate it from other IDs that have the same value (eg. If two rows have a primary key equal to `ott`, but the rows are different, then an index will be added at the end of the second ID, eg. `ott001`, to make sure that all primary key IDs are unique).

#### fn.rownum

Attribute (integer): The zero-based row number of the current row. For example, it is used in the final argument to `fn.makeid` below:

```python
fn.makeid(datEmpty.addresses.country, datEmpty.addresses.pCode, datEmpty.addresses.city[:3], f"{fn.rownum:03d}")
```

#### fn.sourceclass

Attribute (string): The name of the class in the original source database that was used to populate the current row. For example:

```python
if fn.sourceclass == "WWMeasure":
    target = dat.samples.get_first_linked_value("siteID", linkage_path={"source_slot":"sampleID", "target_slot":"sampleID"})
else:
    target = ""
```

#### fn.sourcerow

Attribute (integer): The zero-based row number in the original source database and source class (`fn.sourceclass`) that was used to populate the current row.

#### fn.datetimetz(d)

Convert array of values to a date-time-timezone string in the format YYYY-mm-ddTHH:MM:SS.f+0000 (YYYY=year, mm=month number, dd=day, HH=24-hour time, MM=minutes, SS=seconds, f=ms). For example:

```python3
fn.datetimetz(dat.samples.__collDT.split('/'))
```

An example value of `dat.samples.__collDT` is `2022-11-16/7:00/utc-04:00`, which would result in the output string `2022-11-16T07:00:00-0400`. If the time is empty, then just the date is returned (eg. `2022-11-16`). If the date is empty, then just the time is returned (eg. `07:00:00-0400`). If both are empty, then an empty string is returned. The timezone can also be omitted.
