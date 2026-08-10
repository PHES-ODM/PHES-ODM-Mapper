# Action: expand

Expand multivalued (array) cells so that each item in the array gets its own
row. Optionally select only some of the items first, remove null items, and warn
when an array is longer than expected.

## Where It Fits

`expand` runs wherever the data still contains arrays. In the built-in
`pha4ge-to-v2` module it runs immediately after [`map`](map.md), because mapping
a wide source into long tables can produce cells holding several values. It is
usually followed by [`filter`](filter.md), which removes rows that the expansion
leaves empty.

The `expand` action works on target-format class and slot names when placed
after `map`, so write the config using the names in whichever format the data is
in at that step.

## Example

```yaml
- action: expand
  params:
    config: expander/expander_config.yaml
```

## Parameters

| Parameter | Required/Optional | Description |
| :-------- | :---------------- | :---------- |
| `config` | Required | Path to the expander configuration file, which lists the slots to expand and their options. Module-relative path; may start with `{shared}` or `{temp}`. |

## What Expansion Does

Given a `value` slot holding arrays in the first and last rows:

| measure | value         |
|---------|---------------|
| Orange  | [1, "b", "c"] |
| Blue    | 3             |
| Green   | [5, 6]        |

expanding on `value` produces:

| measure | value    |
|---------|----------|
| Orange  | 1        |
| Orange  | b        |
| Orange  | c        |
| Blue    | 3        |
| Green   | 5        |
| Green   | 6        |

The first three rows come from `[1, "b", "c"]` and the last two from `[5, 6]`.
Values in all other slots are copied unchanged into each new row.

Items can also be selected before expanding. Selecting the first and last items
of each array gives:

| measure | value    |
|---------|----------|
| Orange  | [1, "c"] |
| Blue    | 3        |
| Green   | [5, 6]   |

The middle item `"b"` is gone, and expanding then produces:

| measure | value    |
|---------|----------|
| Orange  | 1        |
| Orange  | c        |
| Blue    | 3        |
| Green   | 5        |
| Green   | 6        |

Because selection can narrow an array to a single item, `expand` is also the way
to reduce a multivalued slot to one value: set `select_items: 0` and, if
desired, `expand: False`.

## Preparing the Config File

The config file has a single top-level key, `expand_columns`. Under it, each key
is a class name and its value is a list of slots in that class to process:

```yaml
expand_columns:
    samples:
        - purpose
        - saMaterial:
            select_items: 0
            remove_nulls: True
            max_length: 1
        - collType:
            select_items: [0, -1]
    sites:
        - sampleShed
```

A list item can be written two ways:

- **A plain string** (`purpose`, `sampleShed`) — expand the slot using every
  value in its arrays, with no options.
- **A single-key dictionary** (`saMaterial`, `collType`) — the key is the slot
  name and the value is a dictionary of the options below.

Classes and slots that are not listed are left untouched. A working example is
[/odm_map/data/modules/pha4ge-to-v2/expander/expander_config.yaml](../../odm_map/data/modules/pha4ge-to-v2/expander/expander_config.yaml).

The options are applied in this order: `remove_nulls`, then `max_length`, then
`select_items`, then `expand`.

| Option | Default | Description |
| :----- | :------ | :---------- |
| `remove_nulls` | `False` | Remove null items and empty strings from the array before anything else. |
| `max_length` | *(none)* | Log an error if the array is longer than this. Makes no change to the data. |
| `select_items` | *(none)* | Index or list of indices to keep from the array. |
| `expand` | `True` | Whether to perform the expansion itself. |

### Expand Option: remove_nulls

Remove all null items and empty strings from the array before selecting and
expanding:

```yaml
expand_columns:
    sites:
        - sampleShed:
            remove_nulls: True
            select_items: -1
```

For example, the sites table:

| sampleShed                   |
|------------------------------|
| ['hosptl', None, 'dorm', ''] |

becomes:

| sampleShed         |
|--------------------|
| ['hosptl', 'dorm'] |

This matters when combined with `select_items` or `max_length`, since removing
the nulls changes which indices are in range and how long the array is.

### Expand Option: max_length

Log an error message telling the user that an array has too many elements. This
option does not modify any data — it only reports. A common use is asserting
that a slot should only ever hold one value:

```yaml
expand_columns:
    sites:
        - sampleShed:
            remove_nulls: True
            max_length: 1
```

`max_length` is checked after `remove_nulls` (so nulls do not count towards the
length) and before `select_items` (so it reports on the array as it arrived, not
on the selection).

### Expand Option: select_items

Select the item(s) at the given index or indices before expanding:

```yaml
expand_columns:
    samples:
        - saMaterial:
            select_items: 0
        - collType:
            select_items: [0, -1]
```

`saMaterial` keeps only the first item, and `collType` keeps the first and last
items. Negative indices behave as they do in Python: `-1` is the last item, `-2`
the second last, and so on.

Indices are resolved per row, since each row's array may be a different length:

- An index that is out of range (at or above the array length, or below the
  negative array length) is dropped.
- An index that refers to an item another index already selected is only counted
  once, including a negative index that maps onto a positive one already listed.

For example, selecting from an array of length 3 with:

```yaml
select_items: [0, 1, 3, -1, -2, -4]
```

drops `3` and `-4` as out of range, leaving:

```yaml
select_items: [0, 1, -1, -2]
```

`-1` refers to index 2, and `-2` refers to index 1 which is already selected, so
the effective selection becomes:

```yaml
select_items: [0, 1, 2]
```

If none of the indices are in range for a row, that row is dropped.

### Expand Option: expand

`expand` performs the actual row expansion and defaults to `True`. Set it to
`False` to apply the other options — removing nulls, checking the length,
selecting items — without splitting the cell into multiple rows:

```yaml
expand_columns:
  sites:
        - sampleShed:
            remove_nulls: True
            max_length: 1
            expand: False
```

This is useful when a downstream step needs the whole array. The `pha4ge-to-v2`
module does this for `sites.sampleShed`: every item must survive because
[`generate_ids`](generate_ids.md) inspects all of them to decide whether each
value belongs in `sampleShed` or `siteType`.

## Related Documentation

- [Pipeline Actions](README.md) — step structure, interpolation variables, and
  path resolution
- [Reference](../reference.md#module-configuration) — the module
  configuration file
- Implementation:
  [/odm_map/actions/action_expand_data.py](../../odm_map/actions/action_expand_data.py),
  [/odm_map/expander/array_expander.py](../../odm_map/expander/array_expander.py)
