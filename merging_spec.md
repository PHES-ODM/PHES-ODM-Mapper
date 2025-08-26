# Merging Mapped Datasets

## Introduction

The PHES-ODM Mapper maps data from a source database format (eg. PHA4GE) to a
target database format (eg. ODM v3). During this mapping, IDs get generated
according to ID generation rules. These IDs become both primary keys and
foreign keys. If a generated primary key is already in use, but the rows using
that primary key are different, then an index (number) gets appended to the
primary key to ensure that it is unique. If instead there are multiple
identical rows with the same primary key, then all the identical rows receive
the same index, and in the end these duplicate rows get dropped, retaining only
one of the duplicates.

The above behaviour is currently implemented and fully functional with the ID
generator of the PHES-ODM Mapper. However, a problem occurs when a user maps a
dataset once, stores that dataset, and then maps a separate dataset and merges
the two separately mapped datasets. Because the two initial datasets are mapped
independently, it's possible that the merged mapped data will have duplicate
primary keys. These primary key conflicts must be avoided, either by adding a
unique index to the primary key or dropping some rows.

The purpose of this document is to spec out how to merge two separate mapped
datasets while avoiding conflicts in primary keys. Most of the code that must
be written will be to initialize the input datasets and programatically create
configurations. Once these are complete, the ID generator (which already
exists) can be run to merge the datasets.

## Terminology

There are two datasets we will consider:

1. Dataset 1: This is mapped data that has been mapped and stored in the past.
2. Dataset 2: This is the new mapped data that we want to merge with Dataset 1.

If the user has multiple datasets to merge with Dataset 1, these datasets can
be appended together to form a larger Dataset 2. Even if there are primary key
conflicts in this new Dataset 2, the method described below will properly deal
with these conflicts.

## Requirements

There are several requirements for merging multiple mapped datasets:

1. Dataset 1 should remain unchanged after merging. This is the "older" data
   that has already been stored. Analysis and sharing may have already been
   performed on this data. As such, we do not want this data to change so that
   any previous analysis and sharing will remain unchanged.
2. Dataset 2 should be merged onto Dataset 1. The primary keys of Dataset 2
   must be modified to avoid primary key conflicts with Dataset 1. The foreign
   keys within Dataset 2 must also be updated to account for the changes in
   primary keys.

## Background

In order to understand how the proposed merging works, it's important to
understand how the ID generator performs linking between tables and how IDs get
generated. The following two sections summarize these steps. If you are already
familiar with the ID generator then you can skip this background section. This
information is also available in the [ID Generator](id_generator.md)
documentation.

### How Linking Works

Linking allows us to determine which primary keys to use for a foreign key
slot. Linking is performed by matching value(s) in the source row of one table
with value(s) in a target row in another table. We then use the primary key in
the matched target row. As an example, suppose we have the following `measures`
table:

| measureRepID   | value | unit | _extra_measureRepID_tag | _extra_row_tag |
|----------------|-------|------|-------------------------|----------------|
| measureCel     | 20   | cel   | temperature             | 0              |
| measureMg      | 30   | mg    | mass                    | 0              |
| measureCel001  | 25   | cel   | temperature             | 1              |
| measureMg001   | 50   | mg    | mass                    | 1              |

and the following `qualityReports` table:

| qualityReportID | measureRepID | qualityFlag | _extra_measureRepID_tag | _extra_row_tag |
|-----------------|--------------|-------------|-------------------------|----------------|
| rep             | ???          | noConcern   | temperature             | 0              |
| rep001          | ???          | noConcern   | mass                    | 1              |

We want to populate `measureRepID` in the `qualityReports` table.
`measureRepID` is a foreign key into the `measures` table, and so we want to
figure out which `measures` primary key to use in the `measureRepID` slot. This
linking is fully configurable and will depend on the use case. We can decide to
link to `measures` by matching both the `_extra_measureRepID_tag` slot and the
`_extra_row_tag` slot (these slots are found in both the `measures` and
`qualityReports` tables above). So for the first row in `qualityReports` (where
the primary key is `rep`), we match the values `temperature` and `0` to extract
the first row in the `measures` table. The retrieved primary key is
`measureCel`. For `rep001`, we match the values `mass` and `1` and extract the
fourth row in the `measures` table. The retrieved primary key is
`measureMg001`. We then get the following table:

| qualityReportID | measureRepID | qualityFlag | _extra_measureRepID_tag | _extra_row_tag |
|-----------------|--------------|-------------|-------------------------|----------------|
| rep             | measureCel   | noConcern   | temperature             | 0              |
| rep001          | measureMg001 | noConcern   | mass                    | 1              |

In this example, the "\_extra\_" columns in the `measures` and `qualityReports`
tables have the same names, but it is possible to use different names between
the tables, as long as they are properly specified in the configuration file.
Indeed, any column can be used, not just "\_extra\_" columns.

These linking rules are specified in a configuration file. There are two ways
to specify linking rules: We can specify that the rule is the default rule to
use for linking between two tables, or we can specify a name for the linking
rule and use that name to specify that we want to use that rule. An example of
a named linking rule called `my_name`, for linking from `qualityReports` to
`measures`, is shown below:

```yaml
named_class_linkages:
  my_name:
    qualityReports:
      measures:
        source_slot: ["_extra_measureRepID_tag", "_extra_row_tag"]
        target_slot: ["_extra_measureRepID_tag", "_extra_row_tag"]
```

### How IDs Get Generated

In order to generate a primary or foreign key value, we run custom Python code
that is defined in an ID code configuration file. Available in the custom code
are various namespaces that provide access to values within the dataset
(usually through linking) and some additional commonly-used functions. As an
example, we'll use the following ID code configuration:

| class          | slot            | code0                                        | code1                                             |
|----------------|-----------------|----------------------------------------------|---------------------------------------------------|
| measures       | measureRepID    | fn.makeid(dat.measures.__measureRepID)       | fn.makeid("measure", datEmpty.measures.unit)      |
| qualityReports | qualityReportID | "rep"                                        |                                                   |
| qualityReports | measureRepID    | dat.measures.measureRepID                    |                                                   |

For a given slot, we calculate the ID using the custom Python code in the
`code0` column. If that code generates a non-empty value, then the value is
used as the ID. If it generates an empty value, then the code in the `code1`
column is used. Any number of `code` columns can be used.

In the above example, we can also see examples of primary keys (the first two
rows) and a foreign key (the last row), as well as how to access linked data
and how to use various specialized functions. The `fn.makeid` function
concatenates a list of strings, changing the capitalization slightly.
`dat.measures.measureRepID` (in the last row) will return the value of
`measureRepID` in the first linked row in the `measures` table. In this case,
the default linking rules will be used. It is possible to specify custom named
linking rules in a configuration file, in which case we would use the
`get_first_linked_value` function to specify the rule, for example:
`dat.measures.get_first_linked_value("measureRepID",
linkage_path="qualityReports_to_measures_temperature")`. In this example, we
would need a named linkage rule called `qualityReports_to_measures_temperature`
in the configuration file.

For the special case where linking is performed from one table to the same
table (rather than a different table), we ignore any linkage rules and instead
return a value from the row we are currently generating an ID for. In the first
row for the example above, we are specifying the code for generating
`measureRepID` in the `measures` table. In the `code0` column we have
`dat.measures.__measureRepID`. In this case, `dat.measures.__measureRepID` will
return the `__measureRepID` value in the `measures` table for the current row
that we are generating IDs for. These slots, preceded by two underscores,
contain the original value that the slot contained before the ID generator was
run (in this case the original value in the `measureRepID` slot).

Notice that there are two namespaces for accessing linked data: `dat` and
`datEmpty`. `dat` will retrieve the linked value unchanged (if the value is
empty it will return an empty value). `datEmpty` will perform some
modifications: If the value is empty, then the string `empty` will be returned,
and if it refers to an ID, the index gets dropped (eg. if the ID is `rep001`,
then `rep` will be returned).

## Methods

The plan is to use the existing ID generator to update the primary and foreign
keys in Dataset 2. Most of the work involves initializing the datasets and
programatically creating the configuration, as the rest of the code has already
been written for the ID generator. The following sections describes how the
configuration must be set up in order for the ID generator to merge the two
datasets. All of these configurations will be generated programatically.

### Initialization of Dataset 1

At the start of typical ID generation, all primary key and foreign key slots
that need to be generated are replaced with `None`. We then iterate over all
these slots to generate the IDs using the ID code configuration file and
additional configuration options (such as linkage paths) from a config file.
Once an ID gets generated, its value is stored in an `IDValue` object and if
required an index is added to the `IDValue` object (to avoid conflicting
primary keys).

To initialize Dataset 1, we will iterate over all primary and foreign key slots
and copy the existing values to an `IDValue` object. We will also initialize
any other data that typically gets generated (eg. hashes for all rows to allow
for fast searching of identical rows, lookup tables for faster searching of
values in certain slots, etc).

### Initialization of Dataset 2

The next sections describe how we will programmatically create the custom ID
generation code, the linkage rules, and the extra slots to facilitate the
linking. Once these configurations are complete we can run the ID generator.

#### ID Generation Code for Primary Keys

The code for the primary keys is simple: we use the `dat` namespace and the
double-underscore version of the slot name for the primary key. Recall that the
double-underscore version refers to the original value of the slot, before we
started ID generation at this stage (remember that our two datasets, before
merging, already have primary and foreign key values, since ID generation was
ran when the initial mapping was performed). For example, the following will
define the code for the primary keys in the `measures`, `samples`, and `sites`
tables:

| class    | slot         | code0                       |
|----------|--------------|-----------------------------|
| measures | measureRepID | dat.measures.__measureRepID |
| samples  | sampleID     | dat.samples.__sampleID      |
| sites    | siteID       | dat.sites.__siteID          |

No special linkage rules need to be defined, since all references in `code0`
are for the same class that that row is for (eg. in the first row `measures` in
the `class` column and `dat.measures.__measureRepID` in the `code0` column both
refer to the `measures` table). Generation of these primary keys will also
trigger generation of any foreign keys in the same row (see the next section),
and, if required, will also trigger the code to append indices to the primary
keys to ensure they are unique.

#### ID Generation Code for Foreign Keys

The code for foriegn keys is also simple: we again use the `dat` namespace to
refer to the correct primary key. In this case, however, we require special
linkage rules and therefore we use the `get_first_linked_value` function so
that we can specify which rules to use. These linkage rules will be described
in the next section.

| class    | slot         | code0                                                                                                       |
|----------|--------------|-------------------------------------------------------------------------------------------------------------|
| measures | protocolID   | dat.protocols.get_first_linked_value("protocolID", linkage_path="measures_protocolID_protocols_protocolID") |
| measures | sampleID     | dat.samples.get_first_linked_value("sampleID", linkage_path="measures_sampleID_samples_sampleID")           |
| sites    | polygonID    | dat.polygons.get_first_linked_value("polygonID", linkage_path="sites_polygonID_polygons_polygonID")         |

#### Linkage Rules and Linking for Foreign Keys

For linking between tables, we add extra slots, outside those specified in the
LinkML schema, to the various data tables we wish to link. We can then populate
these slots with our own custom values. These will provide values to match for
linking to provide a means to determine which primary key to use as a foreign
key. With the ID generator, these extra columns typically start with the string
"\_extra\_", which is the practice we will follow here.

Within Dataset 2 (after it has been initialized and appended to Dataset 1), we
iterate over all foreign keys in all tables. For a given foreign key, we
identify the exact row that the foreign key points to. This is done by finding
the row in the target table that contains the foreign key value as a primary
key. In this row, we set the value in an "\_extra\_" column to a unique
integer. In the source row (where the foreign key is found), we also set the
same "\_extra\_" column to the same integer. This provides a link between the
two rows, by matching the values in the "\_extra\_" column.

To generate the unique integers that act as linking targets, we can use a
counter, and if we're merging multiple Dataset 2s, we can prefix extra unique
identifiers to the integers, such as `dataset_2a_`, `dataset_2b_`, etc., to
further distinguish the various datasets.

Naming of the "\_extra\_" column can follow the following pattern:

```
_extra_sourceClass_sourceSlot_targetClass_targetSlot_tag
```

The values `sourceClass`, `sourceSlot`, `targetClass`, and `targetSlot` take on
their respective values. In the linkage configuration file, we create a linkage
rule named `sourceClass_sourceSlot_targetClass_targetSlot` that specifies to
match the values in the column
`_extra_sourceClass_sourceSlot_targetClass_targetSlot_tag`. This named linkage
rule is used in the ID generation code for the foreign keys when calling the
`get_first_linked_value` function.

Below is an example of how this linkage rule would look like in the
configuration file:

```yaml
named_class_linkages:
  measures_protocolID_protocols_protocolID:
    measures:
      protocols:
        source_slot: ["_extra_measures_protocolID_protocols_protocolID_tag"]
        target_slot: ["_extra_measures_protocolID_protocols_protocolID_tag"]
```

As discussed previously, the ID generation custom code would look like the following:

```python
dat.protocols.get_first_linked_value("protocolID", linkage_path="measures_protocolID_protocols_protocolID")
```

#### Final Steps

We append Dataset 2 to the end of Dataset 1. Once the previous steps have been
completed, we can run the ID generator to generate all primary keys and foreign
keys. We would start at the first row of Dataset 2. The existing code will
properly index duplicated primary keys, and properly ensure that the foreign
keys get modified to use the new primary keys. Dataset 1 will remain unchanged.

## Limitations and Concerns

1. Currently, the ID generator must load all data into memory. This might lead
   to resource issues depending on the user's setup.
2. Each time we merge datasets, the stored dataset gets larger. While there are
   a lot of optimizations in the ID generator, the time to execute should still
   be expected to increase as more data gets merged. Since Dataset 1 is the
   dataset that will grow, and Dataset 1 does not require recalculation of
   primary keys, it is hoped that the increased runtime will be limited.
   Related to point 1, memory requirements will also inrease.
3. Primary keys sometimes get indexed with an integer in order to make them
   unique. For example, `sample001` has the index `001`. When running the ID
   generator to merge datasets, we might end up having to add an additional
   index to an ID in order to make it unique, in which case we would obtain
   something like `sample001002`. It is very unlikely that this would propagate
   to longer and longer IDs, since due to how merging works an index would only
   be added at most twice to an ID. However, having two indices might still be
   undesirable purely in a cosmetic sense. One way to avoid this is to parse
   these trailing digits, and replace them if a new index is required, rather
   than keep them and append a second index. Unfortunately, there is no good
   and universal way of determining if trailing digits are an index, or if they
   are some intrinsic part of the ID. For example, a sample collected on June
   5, 2025, might be given the ID `sample05062025`, in which case `05062025`
   would be mistaken for an index and removed from the sample name. We will try
   both approaches (appending a new index vs replacing an existing index) and
   see which works best, but we suspect the first option will be better. An
   alternate option is to always precede indices with an allowable character
   such as an underscore, which could help reduce (but not fully eliminate) how
   often digits are mistakenly interpreted as an index.
