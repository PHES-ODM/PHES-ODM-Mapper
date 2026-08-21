# Action: select_enum_hierarchy

For multivalued slots whose range includes an enumeration, remove any value in
the cell that is an ancestor of another value in the same cell, keeping only the
most specific values.

## Where It Fits

`select_enum_hierarchy` operates on multivalued cells, so it belongs wherever
the data still holds arrays. In the built-in `pha4ge-to-v3` module it runs after
[`clean`](clean.md) and before [`map`](map.md), on the source data.

It can be run against the target format instead, as long as the `schema`
parameter matches whichever format the data is in at that point.

## Example

```yaml
- action: select_enum_hierarchy
  params:
    schema: schemas/pha4ge.yaml
    config: enum_hierarchy/config.yaml
```

## Parameters

| Parameter | Required/Optional | Description |
| :-------- | :---------------- | :---------- |
| `schema` | Required | Path to the LinkML schema the data belongs to. The enumeration hierarchies are read from this schema. This is a module-relative path and may start with `{shared}` or `{temp}`. |
| `config` | Optional | Path to a YAML config file listing the classes and slots to process. If omitted, **every** multivalued slot with an enumeration range in every class is processed. This is a module-relative path and may start with `{shared}` or `{temp}`. |

## How the Hierarchy Is Determined

The hierarchy comes from the `is_a` attribute of the permissible values in the
LinkML schema, where `is_a` names the **parent** of the value being defined. For
example:

```yaml
enums:
  transportation:
    permissible_values:
      wheeled:
      one_wheeled:
        is_a: wheeled
      unicycle:
        is_a: one_wheeled
      monowheel:
        is_a: one_wheeled
      two_wheeled:
        is_a: wheeled
      bicycle:
        is_a: two_wheeled
      mountain_bike:
        is_a: bicycle
      road_bike:
        is_a: bicycle
      gravel_bike:
        is_a: bicycle
      motorbike:
        is_a: two_wheeled
```

This defines the hierarchy:

```text
- wheeled
  - one_wheeled
    - unicycle
    - monowheel
  - two_wheeled
    - bicycle
      - mountain_bike
      - road_bike
      - gravel_bike
    - motorbike
```

For a multivalued slot that uses the `transportation` enumeration, the selector
produces:

```text
['wheeled', 'monowheel', 'two_wheeled', 'mountain_bike']
      -> ['monowheel', 'mountain_bike']

['two_wheeled', 'mountain_bike', 'road_bike', 'motorbike']
      -> ['mountain_bike', 'road_bike', 'motorbike']
```

In the first example `wheeled` is dropped because `monowheel` and
`mountain_bike` are both descendants of it, and `two_wheeled` is dropped because
`mountain_bike` is a descendant of it. In the second, `mountain_bike` and
`road_bike` are siblings so both are kept, and `motorbike` is on a different
branch so it is kept as well.

Preparing the hierarchy is therefore a matter of adding `is_a` to the
permissible values of the relevant enumerations in the LinkML schema — there is
no separate hierarchy file.

## Preparing the Config File

The config file limits which classes and slots the selector touches. It has a
single top-level `classes` key; under each class name, `slots` lists the slots
to process:

```yaml
classes:
  class1:
    slots:
      - slot1_a
      - slot1_b
      - slot1_c
  class2:
    slots:
      - slot2_a
```

With this config, `slot1_a`, `slot1_b`, and `slot1_c` in `class1` are processed,
as is `slot2_a` in `class2`. Every other class and slot is left alone.

Notes on writing the config:

- A class that is not listed is skipped entirely.
- A slot listed under a class must exist as an attribute of that class in the
  schema, otherwise the run fails.
- Slots listed here are processed whether or not they are multivalued enum
  slots. When `config` is omitted, in contrast, only multivalued slots with at
  least one enumeration in their range are selected automatically.
- Omit `config` altogether (as the `pha4ge-to-v3` module does) to process
  everything eligible. Add a config file when you need to restrict the selector
  to specific slots — for example when one multivalued enum slot deliberately
  carries both a parent and a child value.

## Related Documentation

- [Pipeline Actions](README.md) — step structure, interpolation variables, and
  path resolution
- [Reference](../reference.md#module-configuration) — the module
  configuration file
- Implementation:
  [/odm_map/actions/action_select_enum_hierarchy.py](../../../odm_map/actions/action_select_enum_hierarchy.py),
  [/odm_map/enum_hierarchy/enum_hierarchy_selector.py](../../../odm_map/enum_hierarchy/enum_hierarchy_selector.py)
