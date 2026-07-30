# ID Generator

## Introduction

After the initial mapping step with the LinkML-Map schemas and the filtering
step to remove unwanted rows, IDs can be generated for all rows in the output
tables. These IDs can act as primary and foreign keys, and it can be ensured
that primary keys are all unique. Because ID generation is performed after
mapping it is possible to use the final values in the output to construct the
IDs by combining various values in the rows. When set up properly we can link
rows between the various tables using the generated IDs.

Generating IDs is fairly flexible and can be expressed as short Python code
segments specified in configuration files. It is also possible to generate
non-ID values, such as formatting dates and times correctly.

There are two configuration files that must be created:

1. *General Configuration File*: Specifies some general settings, such as which
   slot is the primary key for each class.
2. *Code Configuration File*: Species the Python code that is executed to
   generate the IDs or values of the various slots.

The location of these files within a conversion module are specified in the
module configuration file ([Custom Modules](custom_modules.md)). See below for
details of both files.

## General Configuration File

This is a simple YAML file that specifies some general configuration. At the
moment the only setting is `primary_keys`, which is a dictionary where the keys
are class names and the values are the single primary key for that class. See
below for an example:

```yaml
primary_keys:
  addresses: addressID
  contacts: contactID
  datasets: datasetID
  # ...
```

## Code Configuration File

The code configuration file specifies the Python code to generate IDs can be
stored in either a CSV file or an Excel file. The following columns should be
included:

1. *class*: The class that the current configuration row is for.
2. *slot*: The slot that the current configuration row is for.
3. *code*: The Python code that is executed to generate the ID for the slot.
   Any column that starts with the word *code* will be considered a code
   column. (eg. "code1", "codeb", etc.). After executing the code, the
   resulting value from code execution will be used. Or if the variable
   "target" is set by the code, then that value is used instead.

For all the mapped data, we generate values according to the configuration, and
populate the specified `slot` within each specified `class`. The code from each
*code* column will be executed starting with the left-most *code* column,
working rightward. If the code for a column generates a non-empty value (or
sets the variable "target" to a non-empty value), that value is used as the ID
for the slot. If an empty value is generated, then the next *code* column is
executed. This is repeated until a non-empty value is generated or the last
code column is executed.

An example configuration table is shown below:

| class     | slot      | code0                     | code1 |
|:----------|:----------|:--------------------------|:------|
| addresses | addressID | dat.addresses.__addressID | fn.makeid(datEmpty.addresses.country, datEmpty.addresses.pCode, datEmpty.addresses.city[:3]) |
| addresses | datasetID | dat.datasets.datasetID    |       |
| measures  | siteID    | dat.measures.__siteID     | <pre style="padding: 0; margin: 0; font-size:90%">if fn.sourceclass == "WWMeasure":<br>    target = dat.samples.get_first_linked_value(<br>                   "siteID",<br>                   linkage_path={"source_slot":"sampleID", "target_slot":"sampleID"}<br>                   )<br>else:<br>    target = ""</pre> |

With the above example, we will iterate over all rows of the table `addresses`,
generating the ID for `addressID` and `datasetID` according to the code in
`code0` and `code1`. In the documentation below, we will say that the current
class is `addresses` and the current row is the zero-based row number being
generated within the `addresses` table. Continuing with the above example, we
will also iterate over all rows in `measures` and generate the ID for `siteID`
according to the code in `code0` and `code1`.

## Linking Between Tables

There are many cases where linking between rows in different output tables is
required. For example, a row in the `measures` table, where a value is recorded
(eg. the population density of a site), would need a `contactID` for who
recorded the population density. In the below example tables, we want to figure
out which `contactID` to use for each row in the `measures` table:

measures table:
| measureRepID         | measure    | value | unit        | contactID | (\_\_source_file_and_row\_\_) |
|----------------------|------------|-------|-------------|-----------|---------------------------|
| measurePopDensity001 | popDensity | 200   | personPerKm | ???       | source.csv/00             |
| measureAmpSize001    | samVol     | 250   | ml          | ???       | source.csv/00             |
| measurePopDensity002 | popDensity | 80    | personPerKm | ???       | source.csv/01             |
| measureAmpSize002    | samVol     | 250   | ml          | ???       | source.csv/01             |

contacts table:
| contactID   | firstName | lastName | (\_\_source_file_and_row\_\_) |
|-------------|-----------|----------|---------------------------|
| kojiYasuda  | Koji      | Yasuda   | source.csv/00             |
| sukiBannayi | Suki      | Bannayi  | source.csv/01             |
| doeLab      | Jane      | Doe      | source.csv/02             |

In the tables above, the column `(__source_file_and_row__)` is added
automatically by the mapper and specifies which source file and row (from the
source dataset) was used to populate each of the rows in the target/output
dataset. The source file would correspond to a table in the source dataset.

The default behaviour when linking tables is to match the
`(__source_file_and_row__)` values. So the first row in the `measures` table
would receive the `contactID` "kojiYasuda" (since the source file and row is
`source.csv/00`). The second row in `measures` would also receive "kojiYasuda",
and the third and fourth rows would receive "sukiBannayi" (since the source
file and row is `source.csv/01`):

measures table:
| measureRepID         | measure    | value | unit        | contactID   | (\_\_source_file_and_row\_\_) |
|----------------------|------------|-------|-------------|-------------|---------------------------|
| measurePopDensity001 | popDensity | 200   | personPerKm | kojiYasuda  | source.csv/00             |
| measureAmpSize001    | samVol     | 250   | ml          | kojiYasuda  | source.csv/00             |
| measurePopDensity002 | popDensity | 80    | personPerKm | sukiBannayi | source.csv/01             |
| measureAmpSize002    | samVol     | 250   | ml          | sukiBannayi | source.csv/01             |

Note that it's possible that there are multiple rows in the `contacts` table
that have the same value in the `(__source_file_and_row__)` column (as with the
`measures` table). Using the default behavior, the first matching row will be
used, but it is possible to configure the ID generator to retrieve one of the
later matching rows. This is discussed more below.

### Custom Linking

The default linking behaviour, as described previously, is to match the value
in the column `(__source_file_and_row__)` between the source and target tables.
It's possible, however, to match by any column, as well as to match by multiple
columns. This is specified in the ID Generator config file, using either the
`class_linkages` top-level key or the `named_class_linkages` top-level key.

#### class_linkages

By specifying values under the `class_linkages` configuration key, you can
override the default linking behaviour of matching the
`(__source_file_and_row__)` column. The general format of this key is:

```yaml
class_linkages:
  source_table:
    target_table:
      source_slot: slot(s) to match (string or list of strings)
      target_slot: slot(s) to match (string or list of strings)
  source_table2:
    target_table2:
      source_slot: ...
      target_slot: ...
  # etc
```

For example, we can replicate the default behaviour of matching the
`(__source_file_and_row__)` columns when linking from the `measures` table to
the `contacts` table using the following:

```yaml
class_linkages:
  measures:
    contacts:
      source_slot: "(__source_file_and_row__)"
      target_slot: "(__source_file_and_row__)"
```

If we wanted to link by matching multiple columns, we could use:

```yaml
class_linkages:
  measures:
    contacts:
      source_slot: ["(__source_file_and_row__)", "_extra_measures_tag"]
      target_slot: ["(__source_file_and_row__)", "_extra_contacts_tag"]
```

With the above example, we would link from `measures` to `samples` by matching
`(__source_file_and_row__)` in both tables along with matching
`_extra_measures_tag` in the `measures` table with `_extra_contacts_tag` in the
`contacts` table. Below is an example:

measures table:
| measureRepID         | measure    | value | unit        | contactID | _extra_measures_tag | (__source_file_and_row__) |
|----------------------|------------|-------|-------------|-----------|---------------------|---------------------------|
| measurePopDensity001 | popDensity | 200   | personPerKm | ???       | collector           | source.csv/00             |
| measureAmpSize001    | samVol     | 250   | ml          | ???       | lab                 | source.csv/00             |
| measurePopDensity002 | popDensity | 80    | personPerKm | ???       | collector           | source.csv/01             |
| measureAmpSize002    | samVol     | 250   | ml          | ???       | lab                 | source.csv/01             |

contacts table:
| contactID   | firstName | lastName | _extra_contacts_tag | (__source_file_and_row__) |
|-------------|-----------|----------|---------------------|---------------------------|
| kojiYasuda  | Koji      | Yasuda   | lab                 | source.csv/00             |
| sukiBannayi | Suki      | Bannayi  | collector           | source.csv/00             |
| johnSmith   | John      | Smith    | lab                 | source.csv/01             |
| janeDoe     | Jane      | Doe      | collector           | source.csv/01             |

For the first row in the `measures` table, the value for
`(__source_file_and_row__)` is `source.csv/00` and the value for
`_extra_measures_tag` is `collector`. In the `contacts` table there are two
rows that match `source.csv/00`, but after also matching `_extra_measures_tag`
in the `measures` table with `_extra_contacts_tag` in the `contacts` table (ie.
`collector`), we now end up with only one matching `contacts` row: the one
where `contactID` is `sukiBannayi`.

##### Linking via Multiple Tables

While uncommon and a bit convoluted, we may want to link from one table to
another via one or more other tables. For example, to link from `measures` to
`contacts` we may first link to `organizations`, ie. using the path `measures`
-> `organizations` -> `contacts`. Below is an example of how this would be
specified in the configuration file:

```yaml
class_linkages:
  measures:
    contacts:
        -  source_class: measures
           source_slot: _extra_measures_tag
           target_class: organizations
           target_slot: _extra_organizations_tag
        -  source_class: organizations
           source_slot: _extra_organizations2_tag
           target_class: contacts
           target_slot: _extra_contacts_tag
```

In the above example, any number of linkages can be specified. We first link
from `measures` to `organizations` by matching `_extra_measures_tag` to
`_extra_organizations_tag`. Note that this might result in multiple rows being
matched. From these matched rows from `organizations`, we then match the column
`_extra_organizations2_tag` with `_extra_contacts_tag` in the `contacts` table.
Any of the values from the possibly multiple `organizations` rows can act as a
match.

#### named_class_linkages

Specifying `class_linkages` will override the default behavior for linking from
a source to a target table, providing a new default linkage. We can also used
named linkages in a similar fashion. These linkages do not override the default
behaviour, but in the ID code generation file they can be used by explicitly
providing the name of the linkage path to use instead of the default behaviour.

The example configuration below will create a linkage named
`custom_measures_to_contact`. If this linkage is explicitly provided, then all
of the linkage paths specified will be used. In this case, there's a custom
linkage from `measures` to `contacts`.

```yaml
named_class_linkages:
  custom_measures_to_contact:
    measures:
      contacts:
        source_slot: ["(__source_file_and_row__)", "_extra_measures_tag"]
        target_slot: ["(__source_file_and_row__)", "_extra_contacts_tag"]
```

The name is usually provided when accessing data in the ID configuration file
using any of the `dat` or `datEmpty` variables, which are described below. An
example would be:

```python
dat.contacts.get_first_linked_value(
    "contactID", linkage_path="custom_measures_to_contact"
)
```

The above example will retrieve the `contactID` from the `contacts` table, from
whatever the current class is (eg. it might be the `measures` class), and would
use the named class linkage `custom_measures_to_contact`. More on `dat` and
`datEmpty` are provided below.

## Code Namespaces

There are several namespaces that can be used in the ID generation code:

1. dat and datEmpty
2. fn

### dat and datEmpty Namespaces

The *dat* and *datEmpty* namespaces provide access to all the target database
tables and slots. Accessing these namespaces will return values from linked
rows. The format is `dat.className.slotName`. For example,
`dat.samples.sampleID` will return the `sampleID` of the *first* linked row in
the `samples` table. In this case, the source class is the class name for the
current row (under the `class` column of the ID code config file) and the
target class is the `className` in `dat.className.slotName`. It will use the
default linkage path specified in the config file under the
[class_linkages](#class_linkages) key, from the source to the target class.

There are two very important differences between *dat* and *datEmpty*:

1. If *dat* is used and the slot is a primary key (eg.
   `dat.contacts.contactID`), then the returned value will also have an index
   associated with it. This index is added to the primary keys in case more
   than one row as the same primary key value, but those rows are not
   identical. It ensures that the primary keys are unique. For example, in the
   following table `contactID` is the primary key. Each row has the same root
   ID for `contactID` (ie. `myContact`). To ensure that the primary keys are
   unique, an index is added to the second and third rows:

    | contactID    | firstName | lastName |
    |--------------|-----------|----------|
    | myContact    | Koji      | Yasuda   |
    | myContact001 | Suki      | Bannayi  |
    | myContact002 | Jane      | Doe      |

    So `dat.contact.contactID` would return the ID with the index (ie.
    `myContact`, `myContact001`, or `myContact002`). On the other hand,
    `datEmpty` will not return the index. In all cases,
    `datEmpty.contacts.contactID` will return `myContact`, even if we link to
    the second or third row.

2. If *datEmpty* is used to access a slot and the value in that slot is blank,
   then the string `empty` will be returned, whereas using `dat` will return an
   empty string.

#### When to use dat vs datEmpty

Whenever you require the exact value of an ID, for example if you're trying to
populate a foreign key to point to a primary key, use the `dat` namespace. In
all other cases, `datEmpty` should be used. For example, if you're trying to
construct an ID based on other IDs, then `datEmpty` should be used. Below is an
example:

| contactID                 | organizationID    | siteID         |
|---------------------------|-------------------|----------------|
| ottawaHospitalCivicCampus | ottawaHospital001 | civicCampus002 |

`contactID` was calculated by combining the `organizationID` and the `siteID`
into a single string. In this case, *datEmpty* should be used (if `dat` were
used instead, then the `contactID` would become
`ottawaHospital001CivicCampus002`). The reason for limiting the use of `dat`
and only using `dat` for foreign keys is that using it will always result in
the index of the primary key to be calculated. In order to calculate the index,
it must determine if the row is unique or not. If it is unique, a new index
must be created. If it is not unique, an existing index from another
already-existing identical row is used. To determine if rows are unique, all
values in that row must be calculated, and within those values if `dat` is used
then it will also trigger other indices to be calculated in other tables. This
triggering of index calculations can propogate and can easily lead to circular
dependencies. Since `datEmpty` does not require the index, it is much less
likely that it would lead to circular dependencies. The `datEmpty` namespace is
especially useful when creating IDs with the `fn.makeid()` function (see
below).

In order to access the value that a slot had BEFORE it was generated, precede
the slot name with two underscores (`__`). For example, if `sampleID` in table
`samples` is generated through the ID config file, then `dat.samples.sampleID`
will return the generated ID, whereas `dat.samples.__sampleID` will return the
original unmodified `sampleID` before it was generated (ie. what `sampleID` was
initially populated with).

#### dat.targetClass.has_column(name)

This function will return True if the target class has the specified column,
False otherwise.

#### dat.targetClass.get_first_linked_value(target_slot, linkage_path=None)

This function will extract the value in `target_slot` for the first linked row
in the target table. The following two operations are equivalent and will
extract the `sampleID` for the linked row in the target table `samples`:

```python
dat.samples.get_first_linked_value("sampleID")
dat.samples.sampleID
```

If `linkage_path` is None, then linking is performed by matching the
`(__source_file_and_row__)` column, or if this behaviour is overridden in the
config file, then the linkage path found under the
[class_linkages](#class_linkages) key will be used.

`linkage_path` can also be a named linkage path (a string). The name refers to
a linkage path specified in the configuration file under the
[named_class_linkages](#named_class_linkages) key.

The `linkage_path` parameter can also be a dictionary of the form:

```python
linkage_path = {
    "source_slot": "sourceSlotName",
    "target_slot": "targetSlotName",
}
```

The `source_slot` and `target_slot` specify which slot(s) to match between the
source and target tables to perform linking, as specified in the
[class_linkages](#class_linkages) section ("sourceSlotName" and
"targetSlotName" can also be arrays of strings, if matching between multiple
columns/slots is desired). The default behaviour is to use
`(__source_file_and_row__)` for both the source and target slots.

It is also possible to link via multiple tables using an array of linkage
paths:

```python
linkage_path = [
    {
        "source_class": "class_a",
        "source_slot": "slot_a",
        "target_class": "class_b",
        "target_slot": "slot_b",
    },
    {
        "source_class": "class_b",
        "source_slot": "slot_b2",
        "target_class": "class_c",
        "target_slot": "slot_c",
    },
    {
        "source_class": "class_c",
        "source_slot": "slot_c2",
        "target_class": "class_d",
        "target_slot": "slot_d",
    },
]
```

This is again the same as found in the ID generator config file, as described
in the [class_linkages](#class_linkages) section above.

### fn Namespace

The *fn* namespace provides various functions and attributes commonly used in
ID generation code.

#### fn.try_float(v)

Try to convert the value `v` to a float. If it cannot be cast to a float then
`v` is returned unchanged. String values with underscores are not valid floats.

#### fn.try_int(v)

Try to convert the value `v` to an integer. If it cannot be cast to a integer
then `v` is returned unchanged. String values with underscores are not valid
integers.

#### fn.makeid(*args)

Concatenate all arguments into a single string and format to be a valid primary
key ID. All characters that are not alphanumeric or underscores are replaced
with underscores. After character replacement, leading and trailing underscores
are returned.

If only one argument is passed to `fn.makeid` then the capitalization is left
unchanged. If more than one argument is passed then the first character of the
first non-empty argument (typically args[0]) is lowercased, while the first
character of all other args are uppercased. For example, the following will
result in the string "MyID" (ie. with no changes in capitalization):

```python
fn.makeid("MyID")
```

The following will result in the string "myIDSecond" (ie. with changes in
capitalization):

```python
fn.makeid("MyID", "second")
```

In practice, each argument is often a result of accessing values through
`datEmpty`, but this is not a requirement. For example:

```python
fn.makeid(
    datEmpty.addresses.country, datEmpty.addresses.pCode, datEmpty.addresses.city[:3]
)
```

If an ID is passed as an argument to `fn.makeid` (eg. `datEmpty.sites.siteID`),
then the ID's index will be removed. The ID's index is an extra number added to
the end of an ID to differentiate it from other IDs that have the same value
(eg. If two rows have a primary key equal to `ott`, but the rows are different,
then an index will be added at the end of the second ID, eg. `ott001`, to make
sure that all primary key IDs are unique). If the unchanged full ID along with
its index is required, then do not pass it to `fn.makeid`.

#### fn.rownum

Attribute (integer): The zero-based row number of the current row. For example,
it is used in the final argument to `fn.makeid` below:

```python
fn.makeid(
    datEmpty.addresses.country,
    datEmpty.addresses.pCode,
    datEmpty.addresses.city[:3],
    f"{fn.rownum:03d}",
)
```

#### fn.sourceclass

Attribute (string): The name of the class in the original source database that
was used to populate the current row. For example:

```python
if fn.sourceclass == "WWMeasure":
    target = dat.samples.get_first_linked_value(
        "siteID", linkage_path={"source_slot": "sampleID", "target_slot": "sampleID"}
    )
else:
    target = ""
```

#### fn.sourcerow

Attribute (integer): The zero-based row number in the original source database
and source class (`fn.sourceclass`) that was used to populate the current row.

#### fn.datetimetz(d)

Convert array of values to a date-time-timezone string in the format
YYYY-mm-ddTHH:MM:SS.f+0000 (YYYY=year, mm=month number, dd=day, HH=24-hour
time, MM=minutes, SS=seconds, f=ms). For example:

```python3
fn.datetimetz(dat.samples.__collDT.split("/"))
```

An example value of `dat.samples.__collDT` is `2022-11-16/7:00/utc-04:00`,
which would result in the output string `2022-11-16T07:00:00-0400`. If the time
is empty, then just the date is returned (eg. `2022-11-16`). If the date is
empty, then just the time is returned (eg. `07:00:00-0400`). If both are empty,
then an empty string is returned. The timezone can also be omitted.

#### fn.class_name and fn.class_shortname

These return the current class and class short name (as strings), respectively.
The class is equivalent to the table name. The class short names are shorter
versions of the full class name. For example, in ODM v3 the `measures` table
has the short name `sas`. The class shortnames are defined in the ID generator
config file. See the `tables_to_shortnames` key in the config file
[odm_map/data/modules/_shared/ids/general_v2_id_code.yaml](general_v2_id_code.yaml)
for an example of how it is configured for ODM v3.

The short names are also used to prefix IDs passed to fn.makeid if the
generated ID does not begin with an alphabetic character.

## Code Selectors

It's possible to specify to use a different code row in the code configuration file. This is done through code selectors. There are two parts to code selectors:

1. The code selector column in the actual data that we are generating IDs for. This column is named `extra_code_selector`. Within this column, a list of comma-separated code selectors can be specified.
2. The code selector markers in the ID generation code config file. This is also a list of comma-separated code selectors, with the code selectors being specified in the `slot` column.

Below is an example of code selectors in the data:

| sampleID  | name | _extra_code_selector |
|-----------|------|----------------------|
| mySample1 |      | pooling,main         |
| mySample2 |      | main                 |
| mySample2 |      | other2               |
| mySample3 |      |                      |

The code selectors above are `pooling` and `main` for the first sample, `main` for the second sample, `other2` for the third sample, and no selector for the fourth sample.

Below is an example of code selectors in the ID generation config file:

| class   | slot               | code                                       |
|---------|--------------------|--------------------------------------------|
| samples | name               | fn.makeid(dat.samples.sampleID, "default") |
| samples | name:pooling       | fn.makeid(dat.samples.sampleID, "pooling") |
| samples | name:main          | fn.makeid(dat.samples.sampleID, "main")    |
| samples | name:other1,other2 | fn.makeid(dat.samples.sampleID, "other")   |

For `mySample1`, with `pooling` and `main` as the selectors, we will first execute the code for `name:pooling`. If that code produces an output, then it will be used to populate the `name` column. If it doesn't produce output, then we will execute the code for `name:main` and use the resulting value.

For `mySample2`, we will only execute the code for `name:main`.

For `mySample3`, we will only execute the code for `name:other1,other2`. Note that if the code selector for `mySample3` was `other1` then the same code for `name:other1,other2` will be executed, since within the comma-separated list of code-selectors we have `other1`.

For `mySample3`, we will only execute the code for `name`.

Note that we can also specify the default (or blank) code selector by using a comma with no value after it. So in the data we are generating code for we can use something like `pooling,,main` to execute code for `name:pooling`, then the default (no code selector) `name`, and finally the code for `name:main`. Using `pooling,main,` with a trailing comma will execute the default `name` code last. This pattern can also be used in the `_extra_code_selector` column.