from typing import Dict, List, Union

from pathlib import Path
import pandas as pd

from linkml_runtime import SchemaView
from linkml_runtime.linkml_model import SlotDefinition


# All tracking slots. These slots are added to the data to map before mapping occurs.
# Slot derivations are also added to all LinkML-Map schemas to copy these tracking slots to
# the output data. This allows us to determine which source class, source row, and source file
# that the output rows were populated from.
class TrackingSlots:
    SOURCE_CLASS = "(__source_class__)"
    SOURCE_ROW = "(__source_row__)"
    SOURCE_FILE = "(__source_file__)"
    SOURCE_FILE_AND_ROW = "(__source_file_and_row__)"


# The data types for TrackingSlots. Default is "string"
TrackingSlotsTypes = {
    TrackingSlots.SOURCE_CLASS: "string",
    TrackingSlots.SOURCE_ROW: "integer",
    TrackingSlots.SOURCE_FILE: "string",
    TrackingSlots.SOURCE_FILE_AND_ROW: "string",
}


def add_tracking_slots_derivations(spec: Dict, target_schema: SchemaView):
    """Add slot derivations for all class derivations in the mapper spec to copy over the tracking columns
    (from TrackingSlots) to the output. The tracking slots include the source class and source row number
    that mapped data was mapped from. It helps with sorting the output and other down-stream operations
    (eg. might be used when generating IDs that depend on which source class the row originated from)

    Args:
        spec (Dict): The mapper spec to add a row number slot derivation to all classes.
        target_schema (SchemaView): The LinkML schema for the target database that the spec maps onto.
    """
    tree_root = [
        c for c, defn in target_schema.all_classes().items() if defn.tree_root
    ][0]

    all_tracking_slots = get_all_tracking_slots()
    for class_name, class_derivation in spec["class_derivations"].items():
        if class_name == tree_root:
            continue

        for col in all_tracking_slots:
            class_derivation["slot_derivations"][col] = {
                "name": col,
                "populated_from": col,
            }


def add_tracking_slots_to_schema(schema: SchemaView):
    """Add all tracking slots to all classes in the schema.

    Tracking slots include the source row number and class name of a row. These get copied over
    to the mapped data so we know which class and row and output row was derived from. It can
    be used for sorting and other downstream operations, such as for ID generation.

    Args:
        schema (SchemaView): The schema to add the tracking slots to (for all classes).
    """
    all_tracking_slots = get_all_tracking_slots()
    for slot_definition in schema.schema.classes.values():
        slot_definition.slots.extend(all_tracking_slots)

    for slot in all_tracking_slots:
        rng = TrackingSlotsTypes.get(slot, "string")
        schema.schema.slots[slot] = SlotDefinition(
            name=slot, from_schema=schema.schema.id, range=rng
        )


def load_schema_with_tracking_slots(schema_file: Union[str, Path]) -> SchemaView:
    """Load the schema and add the tracking slots.

    Args:
        schema_file (Union[str, Path]): The LinkML schema to load and add tracking slots to.

    Returns:
        SchemaView: The loaded schema with tracking slots added.
    """
    schema = SchemaView(schema_file)
    add_tracking_slots_to_schema(schema)
    return schema


def get_all_tracking_slots() -> List[str]:
    """Get all the tracking slots, which are all the columns specified in TrackingSlots.

    Tracking slots include the source row number and class name of a row. These get copied over
    to the mapped data so we know which class and row and output row was derived from. It can
    be used for sorting and other downstream operations, such as for ID generation.

    Returns:
        List[str]: List of all tracking slots.
    """
    return [
        getattr(TrackingSlots, v) for v in vars(TrackingSlots) if not v.startswith("__")
    ]


def add_tracking_columns(df: pd.DataFrame, class_name: str, file: Union[str, Path]):
    # Add the tracking columns (eg. source class and source row), which are used for sorting
    # and other downstream operations such as ID generation.
    # First make sure the tracking columns don't already exist (this would be due to a name
    # conflict, where the source data already has columns with the same name as a tracking
    # column)
    existing_tracking_slots = set(df.columns).intersection(get_all_tracking_slots())
    if len(existing_tracking_slots) > 0:
        raise ValueError(
            f"Loaded data already has one or more columns with the same name as a tracking column: {existing_tracking_slots}"
        )
    df[TrackingSlots.SOURCE_ROW] = df.index
    df[TrackingSlots.SOURCE_CLASS] = class_name
    df[TrackingSlots.SOURCE_FILE] = str(file)
    # We zero-pad the source row number in the SOURCE_FILE_AND_ROW string. This is to ensure if we sort
    # by SOURCE_FILE_AND_ROW the row number will be in the proper order
    # eg. Sorting the strings "2" and "10" will result in the incorrect order ["10", "2"], but sorting the strings
    # "02" and "10" will result in the correct order ["02", "10"].
    max_row_digits = len(str(df[TrackingSlots.SOURCE_ROW].max()))
    if len(df):
        df[TrackingSlots.SOURCE_FILE_AND_ROW] = df.apply(
            lambda x: f"{x[TrackingSlots.SOURCE_FILE]}/{x[TrackingSlots.SOURCE_ROW]:0{max_row_digits}d}",
            axis=1,
        )
    else:
        # The above fails if df is empty, so properly handle it here.
        df[TrackingSlots.SOURCE_FILE_AND_ROW] = None
