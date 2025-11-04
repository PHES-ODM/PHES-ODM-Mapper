"""
# Wide Column Map Maker

The class WideColumnMapMaker takes in expanded wide data (eg. created by WideColumnExpander) and creates
LinkML-Map schemas as well as a LinkML schema to map from the expanded data to an ODM long format.

Expanded wide data has columns in the form tableShortName_attribute:group. For example, mr_organizationID:10.

## Usage

```python
maker = WideColumnMapMaker(
    config="config.yaml",
    source_class_name="odm_wide",
    target_schema="odm_v3.yaml"
    )
source_schema, source_schema_file, mapping_schemas, mapping_schemas_path = maker.make(
    data_file="expanded.csv",
    data_frame=None,
    output_dir="output/"
    )
```

In the above example, the following values are returned from the maker.make call:

1. source_schema: A LinkML schema as a SchemaView.
2. source_schema_file: The path to the LinkML schema that was saved to disk (if output_dir is specified).
3. mapping_schemas: A Dictionary where the keys are names for a schema and the values are single LinkML-Map schemas.
The keys (names) have no real meaning but can be used, as an example, as file names to save the schemas as.
4. mapping_schemas: The directory containing all the LinkML-Map schemas saved to disk (if output_dir is specified).

Running all the schemas on the expanded data will result in multiple rows for multiple tables that can be concatenated
together to get the mapped data in ODM long format.
"""

import os
from typing import Union, Tuple, List, Dict, Optional
from pathlib import Path
import pandas as pd
import yaml
from copy import deepcopy
from dataclasses import asdict

from linkml_runtime import SchemaView
from linkml.utils.schema_builder import SchemaBuilder
from linkml_runtime.linkml_model import SlotDefinition

from odm_map.utils.logger import get_logger
from odm_map.utils.extra_and_tracking_slots import (
    is_tracking_slot,
    get_tracking_slots,
)
from odm_map.utils.general_utils import read_data_frame, TREE_ROOT_CLASS_NAME
from odm_map.utils.schema_utils import (
    get_ranges_of_slot,
    get_slot_definition,
    get_ranges_of_slot_defn,
)

from odm_map.prepare_wide_to_long.wide_column_utils import (
    ConfigKeys,
    WideColumnValues,
    RECOGNIZED_FLAG_PREFIXES,
    get_column_flags,
    get_flag_prefix,
    groups_of_column,
    column_without_flags,
    get_extra_slot_for_flag_prefix,
)

logger = get_logger(__name__)

# Subdirectory in the output directory to put the generated LinkML source schema in.
SCHEMA_SUB_DIR = "schema"


class WideColumnMapMaker:
    def __init__(
        self,
        config: Union[str, Path],
        source_class_name: str,
        target_schema: Union[str, Path, SchemaView],
    ):
        self.source_schema_file: Optional[Path] = None
        self.map_schemas_path: Optional[Path] = None
        self.mapping_schemas: Optional[Dict[str, Dict]] = None

        self.source_class_name = source_class_name

        if isinstance(target_schema, (str, Path)):
            target_schema = SchemaView(target_schema)
        self.target_schema: SchemaView = target_schema

        with open(config, "r") as f:
            self.config = yaml.safe_load(f)

        self.source_schema_builder = SchemaBuilder(self.source_class_name)

        self.source_schema_builder.add_class(
            TREE_ROOT_CLASS_NAME,
            tree_root=True,
            slots=[source_class_name],
            slot_usage={
                source_class_name: SlotDefinition(
                    name=source_class_name,
                    range=source_class_name,
                    multivalued=True,
                    inlined_as_list=True,
                )
            },
        )

    def make(
        self,
        data_file: Union[str, Path],
        data_frame: pd.DataFrame,
        output_dir: Union[str, Path] = None,
    ) -> Tuple[SchemaView, Optional[Path], Dict[str, Dict], Optional[Path]]:
        """Make the LinkML-Map schemas and the LinkML schema for the source dataset, to map
        the expanded source dataset from wide to long format. The expanded source dataset is
        a wide dataset that has been expanded with WideColumnExpander.

        Args:
            data_file (Union[str, Path]): If specified then use this as the source dataset that
                we want to map. This should be in expanded wide format (ie. after expanding the
                original wide format using WideColumnExpander).
            data_frame (pd.DataFrame): If specified then use this as the source dataset. It is
                treated identically to data_file. If data_file is set then data_frame is ignored.
                (ie. only one of data_file or data_frame should be specified)
            output_dir (Union[str, Path], optional): Directory to save the resulting LinkML-Map
                schemas and LinkML-Map source schema to. If None then they are not saved to disk.
                Defaults to None.

        Returns:
            Tuple[SchemaView, Optional[Path], Dict[str, Dict], Optional[Path]]: Tuple
                containing the artifacts and paths to the saved artifacts:
                    source_schema (SchemaView): The constructed LinkML-Schema that should
                        be used as the source schema when mapping from expanded wide to long.
                    source_schema_file (Optional[Path]): If output_dir was provided, then the full
                        path to the saved LinkML-schema associated with source_schema. If output_dir
                        is None then source_schema_file is None.
                    mapping_schemas (Dict[str, Dict]): A dictionary if LinkML-Map schemas, where
                        the keys are unique names for the schema and the values are actual mapping
                        schemas (as dictionaries). Applying all of these mappings chemas to
                        expanded wide data (and concatenating the results as separate rows) will
                        perform a full mapping from the expanded wide to long format.
                    mapping_schemas_path (Optional[Path]): If output_dir was provided, then the
                        directory where all LinkML-Map schemas associated with mapping_schemas
                        were saved. If output_dir is None then mapping_schemas_path is None.
        """
        if data_file:
            data_frame = read_data_frame(
                data_file, keep_default_na=False, na_values=None
            )
        self.df: pd.DataFrame = data_frame

        self.enum_derivations = {}

        self.make_global_class_derivations()
        self.make_grouped_class_derivations()
        self.add_tracking_slots_to_class_derivations()
        self.add_enums_to_source_schema_builder()

        # Make the final source schema
        self.source_schema = SchemaView(self.source_schema_builder.schema)
        self.source_schema_builder = None

        # Make a mapping schema for all the calculated class derivations
        self.make_mapping_schemas_from_class_derivations()
        # Add an enum derivation for all source enums involved in mapping. The enum
        # derivations will just copy the source enum value unchanged (ie. mirror_source=True)
        self.add_enum_derivations_to_mapping_schemas()

        if output_dir:
            self.save(output_dir)

        return (
            self.source_schema,
            self.source_schema_file,
            self.mapping_schemas,
            self.map_schemas_path,
        )

    def add_enums_to_source_schema_builder(self):
        """Add all the enum definitions to the schema builder.

        We will go through all enums that appear as a range of a slot in the schema builder, then copy
        the enum definition (containing the enum's permissible values) from self.target_schema to
        the schema builder.
        """
        # Get all the enums that appear as a range in the schema
        all_enums = []
        schema = SchemaView(self.source_schema_builder.schema)
        for class_name in schema.all_classes().keys():
            class_defn = schema.induced_class(class_name)
            for slot_defn in class_defn.attributes.values():
                ranges = get_ranges_of_slot_defn(slot_defn)
                enum_ranges = [
                    r for r in ranges if r in self.target_schema.all_enums().keys()
                ]
                all_enums.extend(enum_ranges)

        # Drop duplicates
        all_enums = list(dict.fromkeys(all_enums))

        # Add all the enums, from self.target_schema to self.source_schema_builder
        for enum in all_enums:
            enum_defn = self.target_schema.get_enum(enum)
            self.source_schema_builder.add_enum(enum_defn)

    def make_global_class_derivations(self):
        """Make the class derivations for all slots that do not have a group. These are called
        "global" class derivations. Whenever a grouped class derivation is created, it
        also includes the global slot derivations for that class (for the slots that do not
        have a grouped derivation). This does not include tracking slots.
        """
        self.global_class_derivations = {}

        # Make derivations for all columns that do not have a group, and is not a tracking slot.
        global_columns = [
            c
            for c in self.df.columns
            if not groups_of_column(c) and not is_tracking_slot(c)
        ]
        self.make_derivations(
            self.global_class_derivations, global_columns, group_name=None
        )

    def make_grouped_class_derivations(self):
        """Make the class derivations for all slots that have a group. Within each grouped
        class derivation, all columns have the same group.

        The group is the string that follows the colon in the column name. For example,
        mr_protocolID:12 has the group 12. If the column does not have a group then None
        is returned.
        """
        # Gather all column indices. The indices are the numbers that appear after the column name.
        # For example, measure:10 has a group of "10". When mapping, all columns with the
        # same group get mapped together to a single long format row, and each group gets
        # its own LinkML-Map schema (with no overlap with other groups).
        groups = [groups_of_column(c) for c in self.df.columns]
        groups = [c for sub in groups for c in sub]
        # Remove duplicates
        groups = list(dict.fromkeys(groups))

        # Make derivations for each group
        self.class_derivations = {
            None: self.global_class_derivations,
        }
        for column_group in groups:
            cur_class_derivations = {}
            cur_columns = [
                c for c in self.df.columns if column_group in groups_of_column(c)
            ]
            self.make_derivations(
                cur_class_derivations, cur_columns, group_name=column_group
            )

            # Add the global class derivations if required
            for (
                target_class,
                global_derivation,
            ) in self.global_class_derivations.items():
                if target_class in cur_class_derivations:
                    # We want to use the global derivations first, then update/overwrite
                    # slot derivations from cur_class_derivations. This means that
                    # any slot derivation in the global derivation will be overwritten
                    # by a slot derivation in the grouped derivation if one exists.
                    cur_slot_derivations = cur_class_derivations[target_class][
                        "slot_derivations"
                    ]
                    new_slot_derivations = deepcopy(
                        global_derivation["slot_derivations"]
                    )
                    new_slot_derivations.update(cur_slot_derivations)
                    cur_class_derivations[target_class]["slot_derivations"] = (
                        new_slot_derivations
                    )

            self.class_derivations[column_group] = cur_class_derivations

    def add_tracking_slots_to_class_derivations(self):
        """Add slot derivations to all class derivations to copy the tracking slots from the source to
        the target, and also add the tracking slots to the dynamic source schema (that gets built with
        self.source_schema_builder). Tracking slots are the columns found in the TrackingSlots class.
        """
        # Add all tracking slots to all the derivations (copy them over from source to target datasets)
        tracking_slots = get_tracking_slots()
        for cur_derivations in self.class_derivations.values():
            for target_class_name in cur_derivations.keys():
                if target_class_name == TREE_ROOT_CLASS_NAME:
                    continue
                for tracking_slot in tracking_slots:
                    self.add_slot_derivation(
                        cur_derivations,
                        source_class_name=self.source_class_name,
                        source_slot_name=tracking_slot,
                        target_class_name=target_class_name,
                        target_slot_name=tracking_slot,
                    )
        # Add all tracking slots to the source schema
        for tracking_slot in tracking_slots:
            self.add_slot(
                schema_builder=self.source_schema_builder,
                class_name=self.source_class_name,
                slot_name=tracking_slot,
                info_schema=self.target_schema,
                info_class_name=None,
                info_slot_name=None,
                slot_type="string",
                slot_info={},
                replace_if_present=True,
            )

    def make_mapping_schemas_from_class_derivations(self):
        """From all class derivations (in self.class_derivations), create one or more LinkML-Map mapping schemas.

        The resulting schemas will be saved in self.mapping_schemas, where the keys are a unique name given to
        the mapping schema and the keys are the actual mapping schemas (dictionaries).
        """
        # self.mapping_schemas is a dictionary of LinkML-Map schemas, the keys are a unique name given to each
        # LinkML-Map schema, and the keys are the actual mapping schemas. The actual values of the names (keys)
        # have no real meaning, so can be anything as long as they are unique.
        self.mapping_schemas = {}
        # has_non_global_class_derivations contains a list of all target classes that have a non-global
        # derivation, ie. a derivation that has a group.
        # For all of these target classes that has a non-global derivation, we DO NOT save the global derivation
        # in a mapping schema. This is because the global derivation will be present in the non global derivation.
        has_non_global_class_derivations = [
            d for idx, d in self.class_derivations.items() if idx is not None
        ]
        has_non_global_class_derivations = [
            d.keys() for d in has_non_global_class_derivations
        ]
        has_non_global_class_derivations = [
            c for ctop in has_non_global_class_derivations for c in ctop
        ]
        for idx, cur_derivation in self.class_derivations.items():
            # We need a separate mapping schema for each target class. This is because all target classes
            # are populated from self.source_class_name (eg. ODMWide), but LinkML-Map requires all
            # populated from fields for class derivations to be unique.
            for target_class, target_class_derivation in cur_derivation.items():
                if idx is None and target_class in has_non_global_class_derivations:
                    continue
                cur_schema = {
                    "class_derivations": {
                        target_class: target_class_derivation,
                    }
                }
                # Add the tree root derivation
                self.add_tree_root_derivation(cur_schema["class_derivations"])

                schema_name = f"{self.source_class_name}-{target_class}-{idx if idx is not None else 'global'}"
                self.mapping_schemas[schema_name] = cur_schema

    def add_enum_derivations_to_mapping_schemas(self):
        """For all source slots in all mapping schemas, get the enumerations that the slot can take on
        and add a mirror_source=True enum derivation to the mapping schema. This will copy the enumeration
        from the source slot to the target slot.
        """
        # Go through all mapping schemas
        for mapping_schema in self.mapping_schemas.values():
            # Get all enums for all source slots in the mapping schema
            required_enums = []
            for target_class_name, class_derivation in mapping_schema[
                "class_derivations"
            ].items():
                if target_class_name == TREE_ROOT_CLASS_NAME:
                    continue
                source_class_name = class_derivation["populated_from"]
                # Go through all slot derivation
                for slot_derivation in class_derivation["slot_derivations"].values():
                    if "populated_from" not in slot_derivation:
                        continue
                    # Get the ranges of the populated_from slot. For any range that is an enumeration,
                    # add that enumeration name to required_enums
                    source_slot_name = slot_derivation["populated_from"]
                    ranges = get_ranges_of_slot(
                        source_class_name, source_slot_name, self.source_schema
                    )
                    ranges = [r for r in ranges if r in self.source_schema.all_enums()]
                    if len(ranges) > 0:
                        required_enums.extend(ranges)

            # Remove duplicates
            required_enums = list(dict.fromkeys(required_enums))

            # Add a mirror_source=True enum derivation for all required enums
            for source_enum_name in required_enums:
                if "enum_derivations" not in mapping_schema:
                    mapping_schema["enum_derivations"] = {}

                target_enum_name = f"{source_enum_name}_target"
                if target_enum_name in mapping_schema["enum_derivations"]:
                    continue

                enum_derivation = {
                    target_enum_name: {
                        "name": target_enum_name,
                        "mirror_source": True,
                        "populated_from": source_enum_name,
                    }
                }
                mapping_schema["enum_derivations"].update(enum_derivation)

    def add_tree_root_derivation(self, derivation: Dict):
        """Add the tree root derivation to the specified class derivation. The tree root is the
        top-level class that contains all the tables, and is named TREE_ROOT_CLASS_NAME. Its
        slots are the tables, and a slot derivation is added to copy these slots from the
        source dataset to the target dataset.

        Args:
            derivation (Dict): The class derivation to add the tree root derivations to.

        Raises:
            ValueError: Raised if a tree root derivation already exists for one of the target
                classes.
        """
        # Add the tree root derivation if required
        if TREE_ROOT_CLASS_NAME not in derivation:
            derivation[TREE_ROOT_CLASS_NAME] = {
                "name": TREE_ROOT_CLASS_NAME,
            }
        container_derivations = derivation[TREE_ROOT_CLASS_NAME]

        # Add the slot derivations block for the tree root derivation if required
        if "slot_derivations" not in container_derivations:
            container_derivations["slot_derivations"] = {}
        slot_derivations = container_derivations["slot_derivations"]

        # Add a slot derivation for all target classes
        for target_class in derivation.keys():
            if target_class == TREE_ROOT_CLASS_NAME:
                continue
            if target_class in slot_derivations:
                raise ValueError(
                    f"Derivation for class {target_class} already exists in the tree root derivation."
                )
            slot_derivations[target_class] = {
                "name": target_class,
                "populated_from": self.source_class_name,
            }

    def save(
        self, output_dir: Union[str, Path], delete_existing_mappers: bool = True
    ) -> Tuple[Path, Path]:
        """Save the dynamic source schema for the mapping and all the LinkML-Map schemas to disk.

        Args:
            output_dir (Union[str, Path]): The directory to save the source schema and LinkML-Map
                schemas to.
            delete_existing_mappers (bool): If True, then delete all the existing YAML files in
                the output directory before saving the new mapper schemas. This will ensure that
                artifacts from a previous run are no longer present. If they are present, some
                downstream operations may accidentally use the old artifacts along with the
                new ones. This will only be performed in the root of the output_dir; subdirectories
                will not be affected (eg. the subdirectory where the LinkML schema is saved).

        Returns:
            Tuple[Path, Path]: A tuple of two paths where artifacts are saved. This first is the
                path for the YAML file that is the LinkML schema for the source dataset (for mapping
                purposes), and the second is the directory where all the YAML LinkML-Map schemas are
                found for mapping from wide to long.
        """
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        if delete_existing_mappers:
            # Delete existing YAML files in the output directory. This is NOT performed in the
            # subdirectories of the output directory.
            for f in os.listdir(output_dir):
                if os.path.splitext(f)[1].lower() in [".yaml", ".yml"]:
                    os.remove(os.path.join(output_dir, f))

        # Save the schema for the source
        self.source_schema_file = Path(
            os.path.join(
                os.path.join(output_dir, SCHEMA_SUB_DIR),
                "schema.yaml",
            )
        )
        if os.path.dirname(self.source_schema_file):
            os.makedirs(os.path.dirname(self.source_schema_file), exist_ok=True)
        with open(self.source_schema_file, "w") as f:
            yaml.safe_dump(self.source_schema.schema, f)

        # Save all LinkML-Map schemas
        self.map_schemas_path = Path(output_dir)
        for name, derivation in self.mapping_schemas.items():
            with open(os.path.join(self.map_schemas_path, f"{name}.yaml"), "w") as f:
                yaml.safe_dump(derivation, f)

        return self.source_schema_file, self.map_schemas_path

    def get_class_and_slot(self, col: str) -> Tuple[str, str]:
        """From the specified (possibly grouped) wide column, get the class name and the slot that
        the column is for. For example, the column mr_organizationID:12 has a class of
        "measures" (from mr) and a slot of "organizationID". The class and slot must be
        present in the target schema passed to the constructor.

        Args:
            col (str): The column to get the class and slot for.

        Raises:
            ValueError: Raised if the class or slot are not recognized in the LinkML schema passed
                to the constructor.

        Returns:
            Tuple[str, str]: The class name and slot name for the column.
        """
        parts = column_without_flags(col).split(WideColumnValues.COLUMN_PART_SEPARATOR)
        if len(parts) != 2:
            raise ValueError(
                f"Column name must have exactly two parts (separated by '{WideColumnValues.COLUMN_PART_SEPARATOR}'): {col}"
            )

        # Get the class name
        class_name = [
            k
            for k, v in self.config.get(ConfigKeys.TABLES_TO_SHORTNAMES).items()
            if v == parts[0]
        ]
        if len(class_name) == 0:
            raise ValueError(
                f"Unrecognized table short name '{parts[0]}' in column {col}"
            )
        class_name = class_name[0]

        # Make sure the class exists
        if class_name not in self.target_schema.all_class():
            raise ValueError(f"Unrecognized class '{class_name}' in column {col}")

        # Get the slot
        slot_name = parts[1]

        # Make sure the slot exists
        if not get_slot_definition(
            class_name, slot_name, self.target_schema, exception_on_error=False
        ):
            raise ValueError(
                f"Unrecognized slot '{slot_name}' in class '{class_name}' for column {col}"
            )

        return class_name, slot_name

    def get_type_of_slot(
        self, class_name: str, slot_name: str, schema: SchemaView
    ) -> str:
        """Get the base type of the specified slot.

        Enumerations are assuemd to be strings.

        Args:
            class_name (str): The class the slot belongs to.
            slot_name (str): The slot to get the type of.
            schema (SchemaView): The schema to get the type from.

        Returns:
            str: The type of the slot, such as "string", "float", "int", etc.
        """
        ranges = get_ranges_of_slot(
            class_name=class_name, slot_name=slot_name, schema=schema
        )

        # If the range can be an enum, then treat it as a string
        enum_ranges = [r for r in ranges if r in schema.all_enums()]
        ranges = [r for r in ranges if r not in enum_ranges]
        if len(enum_ranges) > 0:
            return "string"

        # If the range is a user-defined type, then get the typeof
        # If there is no typeof, it is its own base type (eg. "string", "float"), so return the type name
        type_ranges = [r for r in ranges if r in schema.all_types()]
        ranges = [r for r in ranges if r not in type_ranges]
        for r in type_ranges:
            type_defn = schema.induced_type(r)
            if type_defn.typeof:
                return type_defn.typeof
            return type_defn.name

        # Unknown range. This usually occurs when the slot is a foreign key, making the range
        # another table
        return "string"

    def get_slot_definition_info_for_ranges(
        self, ranges: Union[str, List[str]]
    ) -> Dict:
        """For the specified ranges, create the slot definition information required to specify
        that a slot can be any of the ranges.

        If a single range is provided, it will be returned as:
            {
                "range": ranges[0]
            }
        If multiple ranges are provided, it will be returned as:
            {
                "any_of": [
                    { "range": range[0] },
                    { "range": range[1] },
                    ...
                ]
            }

        Args:
            ranges (Union[str, List[str]]): Either a single range or a list of one or more ranges.

        Returns:
            Dict: A dictionary that contains the proper slot definition information for a slot that
                can be any of the specified ranges. The result will either have the "range" key set
                (for a single range) or the "any_of" key set (for multiple ranges)
        """
        if isinstance(ranges, str):
            ranges = [ranges]

        if len(ranges) == 0:
            ranges.append("string")

        if len(ranges) == 1:
            return {"range": ranges[0]}

        return {"any_of": [{"range": r} for r in ranges]}

    def get_range_info_of_slot(
        self, slot_defn: Union[SlotDefinition, Dict], schema: SchemaView
    ) -> Dict:
        """Get the range information from the specified slot definition. The range information is stored
        in the slot definition's "range" and "any_of" keys. We will extract this information, and replace any
        range that points to a class with a string.

        If the slot has a single range, it will be returned as:
            {
                "range": range
            }
        If the slot has multiple ranges, it will be returned as:
            {
                "any_of": [
                    { "range": range[0] },
                    { "range": range[1] },
                    ...
                ]
            }

        Args:
            slot_defn (Union[SlotDefinition, Dict]): The slot definition to get the range info from.
            schema (SchemaView): The schema that the slot belongs to. If any of the ranges are a class
                in this schema, then the range will be converted to a string (since in the final
                schema that we build we will not have those class definitions).

        Returns:
            Dict: A dictionary that contains the range information extracted from the slot definition.
                Either the "range" key (if there is only one range) or "any_of" key (if there is more
                than one range) will be set.
        """
        if isinstance(slot_defn, SlotDefinition):
            slot_defn = asdict(slot_defn)

        # Get an array of all ranges (get them from the "range" and "any_of" slots)
        rng = slot_defn.get("range", None)
        any_of = slot_defn.get("any_of", [])

        if any_of:
            ranges = [d.get("range", None) for d in any_of]
        else:
            ranges = [rng]

        # Replace any ranges that are a class (ie a foreign key) with "string"
        classes = schema.all_classes().keys()
        ranges = [r if r not in classes else "string" for r in ranges]

        # Drop duplicates
        ranges = list(dict.fromkeys(ranges))

        return self.get_slot_definition_info_for_ranges(ranges)

    def add_slot(
        self,
        schema_builder: SchemaBuilder,
        class_name: str,
        slot_name: str,
        info_schema: SchemaView,
        info_class_name: Optional[str],
        info_slot_name: Optional[str],
        slot_type: Optional[Union[str, List[str]]] = None,
        slot_info: Dict = None,
        replace_if_present: bool = False,
    ):
        """Add the specified class and slot to the schema being built by schema_builder.

        Args:
            schema_builder (SchemaBuilder): The SchemaBuilder to add the class and slot to.
            class_name (str): The name of the class to add.
            slot_name (str): The name of the slot to add.
            info_schema (SchemaView): The schema to use for determining the range, description, title, and
                other information about the slot when using info_class_name and info_slot_name.
            info_class_name (Optional[str]): If slot_type is None, then use this plus info_slot_name to determine the
                range, description, title and other info about the slot. This information will be inherited
                from the slot info_slot_name in the schema info_schema.
            info_slot_name (Optional[str]): If slot_type is None, then use this plus info_class_name to determine the
                range, description, title and other info about the slot. This information will be inherited
                from the slot info_slot_name in the schema info_schema.
            slot_type (Optional[Union[str, List[str]]], optional): If specified, then use this type or types
                (eg. "string", "float") to assign as ranges to the slot being added. If None, then we use the
                type of info_class_name and info_slot_name in the info_schema. Defaults to None.
            slot_info (Dict, optional): If specified, then use the values in this dictionary as information to add
                to the new slot being added. It can contain keys and values for "description", "title", and "notes".
                Defaults to None.
            replace_if_present (bool, optional): If True and the slot already exists in the SchemaBuilder, the
                replace the existing slot with the new information. If False then raise an exception if the slot
                already exists in the SchemaBuilder. Defaults to False.
        """
        if slot_type is not None:
            slot_ranges = self.get_slot_definition_info_for_ranges(slot_type)
        elif slot_info is None:
            slot_info = get_slot_definition(
                info_class_name, info_slot_name, schema=info_schema
            )
            slot_ranges = self.get_range_info_of_slot(slot_info, schema=info_schema)

        if slot_info is None:
            slot_info = {}

        # Set the range info in slot_info
        if "range" in slot_info:
            del slot_info["range"]
        if "any_of" in slot_info:
            del slot_info["any_of"]
        slot_info.update(slot_ranges)

        # Select only certain keys for slot_info
        slot_info = {
            k: slot_info.get(k, None)
            for k in ["description", "title", "notes", "range", "any_of"]
        }

        if class_name not in schema_builder.schema.classes:
            schema_builder.add_class(class_name)
        schema_builder.add_slot(
            slot_name, class_name, replace_if_present=replace_if_present, **slot_info
        )

    def add_slot_derivation(
        self,
        class_derivations: Dict,
        source_class_name: str,
        source_slot_name: str,
        target_class_name: str,
        target_slot_name: str,
    ):
        """Add a slot derivation to the specified class derivation for copying a source class/slot
        to a target class/slot.

        Args:
            class_derivations (Dict): The class derivations to add the derivation to. This is a
                dicitonary where the keys are the target class and the values are the derivations
                for that class.
            source_class_name (str): The source class to copy from.
            source_slot_name (str): The source slot (in the source class) to copy from.
            target_class_name (str): The target class to copy to.
            target_slot_name (str): The target slot (in the target class) to copy to.

        Raises:
            ValueError: A slot derivation for the target class/slot already exists.
        """
        # Add top-level class derivation for class_name if not present
        if target_class_name not in class_derivations:
            class_derivations[target_class_name] = {
                "name": target_class_name,
                "populated_from": source_class_name,
            }
        class_derivation = class_derivations[target_class_name]

        # Add top-level slot derivations if not present
        if "slot_derivations" not in class_derivation:
            class_derivation["slot_derivations"] = {}
        slot_derivations = class_derivation["slot_derivations"]

        # Make sure mapping from source slot to target slot doesn't already exist
        if target_slot_name in slot_derivations:
            prev_populated_from = slot_derivations[target_slot_name].get(
                "populated_from"
            )
            logger.error(
                f"Slot derivation for {target_class_name}.{target_slot_name} already exists. New populated from {source_class_name}.{source_slot_name}. Previously populated from {target_class_name}.{prev_populated_from}. Overwriting the derivation with the new value."
            )

        # Add mapping from source slot to target slot
        slot_derivations[target_slot_name] = {
            "name": target_slot_name,
            "populated_from": source_slot_name,
        }

    def make_derivations(
        self, class_derivations: Dict, columns: List[str], group_name: Optional[str]
    ):
        """Add class/slot derivations for all columns, to copy from the column to the corresponding
        class/slot. This will also add the slot to the dynamics schema being built for the source
        data (ie. in the SchemaBuilder self.source_schema_builder).

        The class/slot for each column must exist in the target schema passed to the constructor,
        otherwise an exception is raised.

        Args:
            class_derivations (Dict): The class derivations to add the new derivations for the
                columns to. The keys are the target class and the values are the derivation for
                the target class.
            columns (List[str]): All the columns to make a derivation for. For example, the
                column mr_organizationID:1 will add a derivation to copy from the column
                mr_organizationID:1 to the column organizationID in the target class measure (mr).
            group_name (Optional[str]): The group that the derivations belong to. Each class
                derivation has a group associated with it. It is used to populate and extra column
                with the group name, which can be used for linking purposes.
        """
        flags = {}
        for col in columns:
            target_class_name, target_slot_name = self.get_class_and_slot(col)

            if target_class_name is None or target_slot_name is None:
                continue

            cur_flags = get_column_flags(col)
            for flag in cur_flags:
                flag_prefix = get_flag_prefix(flag)
                if target_class_name not in flags:
                    flags[target_class_name] = {}
                if flag_prefix not in flags[target_class_name]:
                    flags[target_class_name][flag_prefix] = []
                flags[target_class_name][flag_prefix].append(flag)

            # Map from col to class_name.slot_name
            self.add_slot_derivation(
                class_derivations,
                source_class_name=self.source_class_name,
                source_slot_name=col,
                target_class_name=target_class_name,
                target_slot_name=target_slot_name,
            )
            self.add_slot(
                schema_builder=self.source_schema_builder,
                class_name=self.source_class_name,
                slot_name=col,
                info_schema=self.target_schema,
                info_class_name=target_class_name,
                info_slot_name=target_slot_name,
            )

        # Add expr to populate all the recognized flags (eg. the groups)
        for target_class in class_derivations:
            slot_derivations = class_derivations[target_class]["slot_derivations"]
            for flag_prefix in RECOGNIZED_FLAG_PREFIXES:
                extra_slot = get_extra_slot_for_flag_prefix(flag_prefix)
                cur_flags = flags.get(target_class, {}).get(flag_prefix, [])
                cur_flags = list(dict.fromkeys(cur_flags))
                cur_flags = ",".join(cur_flags)
                slot_derivations[extra_slot] = {
                    "name": extra_slot,
                    "expr": f"'{cur_flags}'",
                }
