import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import Dict, List, Union, Optional

from pathlib import Path
import pandas as pd

from linkml_runtime import SchemaView
from linkml_runtime.linkml_model import SlotDefinition

from utils.clean_exit_error import CleanExitError
from utils.schema_utils import (
    all_classes_without_tree_root,
    validate_columns_with_schema,
)
from progress import ProgressCounter, EmptyCounter
from utils.general_utils import read_data_frame, EXCEL_FILE_KEY, EXCEL_SHEET_KEY
from utils.logger import get_logger

logger = get_logger(__name__)


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


def load_data_with_tracking_columns(
    data_files: Dict[str, List[Union[str, Path, Dict[str, str]]]],
    schema: Union[SchemaView, str, Path] = None,
    max_rows: Optional[int] = 0,
    random_sample_data: bool = False,
    progress_id: Optional[str] = None,
    add_all_tracking_columns: bool = False,
    validate_class_names: bool = False,
    validate_columns: bool = False,
) -> Dict[str, List[pd.DataFrame]]:
    """Load all data from disk (as DataFrames) and add the tracking columns.

    Args:
        data_files (Dict[str, List[Union[str, Path]]]): Dictionary of all files to load. The keys are the class
            names and the values are lists of files belonging to that class.
        source_schema_file (Union[str, Path]): The source schema that contains the classes that the data_files
            should belong to. Only files belonging to recognized classes are loaded.
        max_rows (Optional[int], optional): Maximum number of rows to load from each file. If 0 or None then all
            rows are loaded. Defaults to 0.

    Returns:
        Dict[str, List[pd.DataFrame]]: The loaded DataFrames. The keys are the class names and the values
            are lists of DataFrames belonging to that class. The order of the DataFrames within each class are the
            same as the order of the files in data_files for the same class.
    """
    if not data_files:
        raise CleanExitError("No input data found.")

    if isinstance(schema, (str, Path)):
        schema = SchemaView(schema)

    if schema is not None:
        recognized_classes = all_classes_without_tree_root(schema)
    else:
        recognized_classes = None

    # Check for invalid class names
    if validate_class_names and schema is not None:
        has_unrecognized_class = False
        for class_name, files in data_files.items():
            if class_name not in recognized_classes:
                has_unrecognized_class = True
                for file in files:
                    logger.error(f"Unrecognized input table '{class_name}': {file}")
        if has_unrecognized_class:
            tables = ", ".join(sorted(recognized_classes, key=lambda x: str(x).lower()))
            msg = f"Terminating due to unrecognized table(s). Allowable tables are: {tables}"
            raise CleanExitError(msg)

    total_items = sum([len(d) for d in data_files.values()])
    if progress_id:
        progress = ProgressCounter({progress_id: total_items}, multiple_bars=False)
    else:
        progress = EmptyCounter()

    warning_log = []
    with progress:
        data_frames = {}
        for class_name, files in data_files.items():
            if validate_class_names and recognized_classes is not None:
                if class_name not in recognized_classes:
                    # Unrecognized class name, so ignore the file (but tell the user)
                    for file in files:
                        logger.info(
                            f"Ignoring file from unrecognized table '{class_name}': {file}"
                        )
                        progress.update(progress_id, 1)
                    continue
            if class_name not in data_frames:
                data_frames[class_name] = []
            for file in files:
                try:
                    if isinstance(file, Dict):
                        track_file = f"{file[EXCEL_FILE_KEY]}:{file[EXCEL_SHEET_KEY]}"
                    else:
                        track_file = file
                    read_kwargs = {
                        "nrows": None
                        if random_sample_data
                        else (max_rows if max_rows else None),
                        "keep_default_na": False,
                        "na_values": None,
                    }
                    df = read_data_frame(file=file, **read_kwargs)
                except pd.errors.EmptyDataError:
                    logger.warning(
                        f"Empty file found for table '{class_name}', ignoring: {track_file}"
                    )
                    df = None
                except FileNotFoundError:
                    raise CleanExitError(f"Specified file does not exist: {track_file}")

                if df is not None:
                    if validate_columns and schema is not None:
                        new_log = validate_columns_with_schema(
                            df, schema=schema, class_name=class_name, file=track_file
                        )
                        warning_log.extend(new_log)

                    # Add tracking columns
                    if add_all_tracking_columns:
                        add_tracking_columns(df, class_name, track_file)

                    data_frames[class_name].append(df)

                    logger.info(
                        f"Loaded {len(df)} rows for table '{class_name}': {track_file}"
                    )

                progress.update(progress_id, 1)

    if warning_log:
        for msg in warning_log:
            logger.warning(msg)

    if len(data_frames) == 0:
        tables = ", ".join(sorted(recognized_classes))
        msg = f"No recognized tables loaded. Allowable tables are: {tables}"
        raise CleanExitError(msg)

    return data_frames
