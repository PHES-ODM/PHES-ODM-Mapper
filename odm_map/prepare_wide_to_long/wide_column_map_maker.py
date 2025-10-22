"""
# Wide Column Map Maker

The class WideColumnMapMaker takes in expanded wide data (eg. created by WideColumnExpander) and creates
LinkML-Map schemas as well as a LinkML schema to map from the expanded data to an ODM long format.

Expanded wide data has columns in the form tableShortName_attribute:index. For example, mr_organizationID:10.

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

1. source_schema: A LinkML schema in dictionary form.
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

from linkml_runtime import SchemaView
from linkml.utils.schema_builder import SchemaBuilder
from linkml_runtime.linkml_model import SchemaDefinition, SlotDefinition

from odm_map.utils.logger import get_logger
from odm_map.utils.extra_and_tracking_slots import is_tracking_slot, get_tracking_slots
from odm_map.utils.general_utils import read_data_frame, TREE_ROOT_CLASS_NAME
from odm_map.prepare_wide_to_long.wide_column_data import (
    ConfigKeys,
    WideColumnValues,
    COLUMN_INDEX_SEPARATOR,
)
from odm_map.utils.schema_utils import get_ranges_of_slot, get_slot_definition

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
    ) -> Tuple[SchemaDefinition, Optional[Path], Dict[str, Dict], Optional[Path]]:
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
            Tuple[SchemaDefinition, Optional[Path], Dict[str, Dict], Optional[Path]]: Tuple
                containing the artifacts and paths to the saved artifacts:
                    source_schema (SchemaDefinition): The constructed LinkML-Schema that should
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

        self.make_global_class_derivations()
        self.make_indexed_class_derivations()
        self.add_tracking_slots_to_class_derivations()
        self.make_mapping_schemas_from_class_derivations()
        if output_dir:
            self.save(output_dir)

        return (
            self.source_schema_builder.schema,
            self.source_schema_file,
            self.mapping_schemas,
            self.map_schemas_path,
        )

    def index_of_column(self, col: str) -> Optional[int]:
        """Get the index of the specified column.

        The index is the number that follows the colon in the column name. For example,
        mr_protocolID:12 has the index 12. If the column does not have an index the None
        is returned.

        Args:
            col (str): The column name to get the index of.

        Returns:
            Optional[int]: The index of the column, or None if no index exists.
        """
        if (
            COLUMN_INDEX_SEPARATOR in col
            and col.split(COLUMN_INDEX_SEPARATOR)[-1].isdigit()
        ):
            return int(col.split(COLUMN_INDEX_SEPARATOR)[-1])
        return None

    def remove_column_index(self, col: str) -> str:
        """Get the column name with the index removed, if there is one.

        The index is the number that follows the colon in the column name. For example,
        mr_protocolID:12 has the index 12. If the column does not have an index the None
        is returned.

        Args:
            col (str): The column to remove the index from.

        Returns:
            str: The column with the index removed.
        """
        if (
            COLUMN_INDEX_SEPARATOR in col
            and col.split(COLUMN_INDEX_SEPARATOR)[-1].isdigit()
        ):
            return col.rsplit(COLUMN_INDEX_SEPARATOR, maxsplit=1)[0]
        return col

    def make_global_class_derivations(self):
        """Make the class derivations for all slots that do not have an index. These are called
        "global" class derivations. Whenever an indexed class derivation is created, it must
        also include the global slot derivations for that class. This does not include
        tracking slots.
        """
        self.global_class_derivations = {}

        # Make derivations for all columns that do not have an index, and is not a tracking slot.
        global_columns = [
            c
            for c in self.df.columns
            if self.index_of_column(c) is None and not is_tracking_slot(c)
        ]
        self.make_derivations(self.global_class_derivations, global_columns)

    def make_indexed_class_derivations(self):
        """Make the class derivations for all slots that have an index. Within each indexed
        class derivation, all columns have the same index.

        The index is the number that follows the colon in the column name. For example,
        mr_protocolID:12 has the index 12. If the column does not have an index the None
        is returned.
        """
        # Gather all column indices. The indices are the numbers that appear after the column name.
        # For example, measure:10 has an index of "10". When mapping, all columns with the
        # same index get mapped together to a single long format row, and each index gets
        # its own LinkML-Map schema (with no overlap with other indices).
        indices = [self.index_of_column(c) for c in self.df.columns]
        indices = [c for c in indices if c is not None]
        # Remove duplicates
        indices = list(dict.fromkeys(indices))

        # Make derivations for each index
        self.class_derivations = {
            None: self.global_class_derivations,
        }
        for column_index in indices:
            cur_class_derivations = {}
            cur_columns = [
                c for c in self.df.columns if self.index_of_column(c) == column_index
            ]
            self.make_derivations(cur_class_derivations, cur_columns)

            # Add the global class derivations if required
            for (
                target_class,
                global_derivation,
            ) in self.global_class_derivations.items():
                if target_class in cur_class_derivations:
                    # We want to use the global derivations first, then update/overwrite
                    # slot derivations from cur_class_derivations. This means that
                    # any slot derivation in the global derivation will be overwritten
                    # by a slot derivation in the indexed derivation if one exists.
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

            self.class_derivations[column_index] = cur_class_derivations

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
                self.source_schema_builder,
                self.source_class_name,
                tracking_slot,
                type_class_name=None,
                type_slot_name=None,
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
        # derivation, ie. a derivation that has an index.
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
            yaml.safe_dump(self.source_schema_builder.as_dict(), f)

        # Save all LinkML-Map schemas
        self.map_schemas_path = Path(output_dir)
        for name, derivation in self.mapping_schemas.items():
            with open(os.path.join(self.map_schemas_path, f"{name}.yaml"), "w") as f:
                yaml.safe_dump(derivation, f)

        return self.source_schema_file, self.map_schemas_path

    def get_class_and_slot(self, col: str) -> Tuple[str, str]:
        """From the specified (possibly indexed) wide column, get the class name and the slot that
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
        parts = self.remove_column_index(col).split(
            WideColumnValues.COLUMN_PART_SEPARATOR
        )
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

    def add_slot(
        self,
        schema_builder: SchemaBuilder,
        class_name: str,
        slot_name: str,
        type_class_name: Optional[str],
        type_slot_name: Optional[str],
        slot_type: Optional[str] = None,
        slot_info: Dict = None,
        replace_if_present: bool = False,
    ):
        """Add the specified class and slot to the schema being built by schema_builder.

        Args:
            schema_builder (SchemaBuilder): The SchemaBuilder to add the class and slot to.
            class_name (str): The name of the class to add.
            slot_name (str): The name of the slot to add.
            type_class_name (Optional[str]): If slot_type is None, then use this plus type_slot_name to determine the
                type that the slot should be (eg. "string", "float", etc). To determine the type, we get the type of the
                type_class_name and type_slot_name from the target schema. If slot_info is None, then we get the info
                (such as the title, description, notes, etc) to assign to the slot from the slot definition for
                type_class_name and type_slot_name.
            type_slot_name (Optional[str]): If slot_type is None, then use this plus type_class_name to determine the
                type that the slot should be (eg. "string", "float", etc). To determine the type, we get the type of the
                type_class_name and type_slot_name from the target schema. If slot_info is None, then we get the info
                (such as the title, description, notes, etc) to assign to the slot from the slot definition for
                type_class_name and type_slot_name.
            slot_type (Optional[str], optional): If specified, then use this type (eg. "string", "float") to assign to
                the slot being added. If None, then we use the type of type_class_name and type_slot_name in the target
                schema. Defaults to None.
            slot_info (Dict, optional): If specified, then use the values in this dictionary as information to add
                to the new slot being added. It can contain keys and values for "description", "title", and "notes".
                Defaults to None.
            replace_if_present (bool, optional): If True and the slot already exists in the SchemaBuilder, the
                replace the existing slot with the new information. If False then raise an exception if the slot
                already exists in the SchemaBuilder. Defaults to False.
        """
        if slot_type is None:
            slot_type = self.get_type_of_slot(
                type_class_name, type_slot_name, schema=self.target_schema
            )
        if slot_info is None:
            slot_info = get_slot_definition(
                type_class_name, type_slot_name, schema=self.target_schema
            )

        if class_name not in schema_builder.schema.classes:
            schema_builder.add_class(class_name)
        schema_builder.add_slot(
            slot_name,
            class_name,
            range=slot_type,
            description=slot_info.get("description", None),
            title=slot_info.get("title", None),
            notes=slot_info.get("notes", None),
            replace_if_present=replace_if_present,
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
            raise ValueError(
                f"Slot derivation for {target_class_name}.{target_slot_name} (from {source_class_name}.{source_slot_name}) already exists."
            )

        # Add mapping from source slot to target slot
        slot_derivations[target_slot_name] = {
            "name": target_slot_name,
            "populated_from": source_slot_name,
        }

    def make_derivations(self, class_derivations: Dict, columns: List[str]):
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
        """
        for col in columns:
            target_class_name, target_slot_name = self.get_class_and_slot(col)

            if target_class_name is None or target_slot_name is None:
                continue

            # Map from col to class_name.slot_name
            self.add_slot_derivation(
                class_derivations,
                source_class_name=self.source_class_name,
                source_slot_name=col,
                target_class_name=target_class_name,
                target_slot_name=target_slot_name,
            )
            self.add_slot(
                self.source_schema_builder,
                self.source_class_name,
                col,
                type_class_name=target_class_name,
                type_slot_name=target_slot_name,
            )
