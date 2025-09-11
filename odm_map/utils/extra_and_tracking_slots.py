from typing import Dict, List, Union, Optional

from pathlib import Path
import pandas as pd

from linkml_runtime import SchemaView
from linkml_runtime.linkml_model import SlotDefinition

from odm_map.utils.clean_exit_error import CleanExitError
from odm_map.utils.schema_utils import (
    all_classes_without_tree_root,
    validate_columns_with_schema,
    find_class,
)
from odm_map.progress import ProgressCounter, EmptyCounter
from odm_map.utils.schema_caster import SchemaCaster
from odm_map.utils.general_utils import read_data_frame, EXCEL_FILE_KEY
from odm_map.utils.logger import get_logger

logger = get_logger(__name__)

# All tracking slots are of the form f"{TRACKING_SLOT_PREFIX}slot_name{TRACKING_SLOT_SUFFIX}"
TRACKING_SLOT_PREFIX = "(__"
TRACKING_SLOT_SUFFIX = "__)"

EXTRA_SLOT_PREFIX = "_extra_"
EXTRA_SLOT_SUFFIX = ""


def make_tracking_slot_name(name: str) -> str:
    """Create a tracking slot name based on the specified name.

    Args:
        name (str): The name to create a tracking slot from.

    Returns:
        str: The tracking slot with the specified name. This is in the format
            f"{TRACKING_SLOT_PREFIX}slot_name{TRACKING_SLOT_SUFFIX}"
    """
    return f"{TRACKING_SLOT_PREFIX}{name}{TRACKING_SLOT_SUFFIX}"


# Predefined tracking slots. These slots are added to the data to map before mapping occurs.
# Slot derivations are also added to all LinkML-Map schemas to copy these tracking slots to
# the output data. This allows us to determine which source class, source row, and source file
# that the output rows were populated from.
# Additional tracking slots might also be present in the data. Any column that start with
# TRACKING_SLOT_PREFIX and ends with TRACKING_SLOT_SUFFIX is considered a tracking slot.
class TrackingSlots:
    SOURCE_CLASS = make_tracking_slot_name("source_class")
    SOURCE_ROW = make_tracking_slot_name("source_row")
    SOURCE_FILE = make_tracking_slot_name("source_file")
    SOURCE_FILE_AND_ROW = make_tracking_slot_name("source_file_and_row")


# The data types for TrackingSlots. These correspond to valid LinkML ranges, such as "string"
# and "integer". Any tracking slot not listed here will have the default data type "string"
TrackingSlotsTypes = {
    TrackingSlots.SOURCE_CLASS: "string",
    TrackingSlots.SOURCE_ROW: "integer",
    TrackingSlots.SOURCE_FILE: "string",
    TrackingSlots.SOURCE_FILE_AND_ROW: "string",
}


def is_extra_or_tracking_slot(c: str) -> bool:
    """Determine if the column is an extra/tracking slot. Tracking slots are all slots that start with
    TRACKING_SLOT_PREFIX and end with TRACKING_SLOT_SUFFIX, and extra slots are all slots that
    start with EXTRA_SLOT_PREFIX and end with EXTRA_SLOT_SUFFIX.

    Args:
        c (str): The slot to test.

    Returns:
        bool: True if c is a tracking slot, False otherwise.
    """
    return is_extra_slot(c) or is_tracking_slot(c)


def is_extra_slot(c: str) -> bool:
    """Determine if the column is an extra slot. extra slots are all slots that start with EXTRA_SLOT_PREFIX
    and end with EXTRA_SLOT_SUFFIX. They can contain any values that we may need downstream of mapping,
    where the mapping that defines their contents are specified in the LinkML mapping files.

    Args:
        c (str): The slot to test.

    Returns:
        bool: True if c is an extra slot.
    """
    return c.startswith(EXTRA_SLOT_PREFIX) and c.endswith(EXTRA_SLOT_SUFFIX)


def is_tracking_slot(c: str) -> bool:
    """Determine if the column is a tracking slot. Tracking slots are all slots that start with
    TRACKING_SLOT_PREFIX and end with TRACKING_SLOT_SUFFIX. They define which rows/columns in the
    source dataset that was used to generate a row in the target dataset.

    Args:
        c (str): The column to test.

    Returns:
        bool: True if c is a tracking slot.
    """
    return c.startswith(TRACKING_SLOT_PREFIX) and c.endswith(TRACKING_SLOT_SUFFIX)


def drop_extra_slots(df: pd.DataFrame) -> pd.DataFrame:
    """Drop all the extra columns in the specified DataFrame.

    These are columns that start with the string extra_and_tracking_slots.EXTRA_SLOT_PREFIX and end with the
    string extra_and_tracking_slots.EXTRA_SLOT_SUFFIX.

    Args:
        df (pd.DataFrame): The DataFrame to drop the extra columns from.

    Returns:
        pd.DataFrame: The copy of df with all the extra columns dropped.
    """
    drop_cols = [c for c in df.columns if is_extra_slot(c)]
    df = df.drop(drop_cols, axis=1)
    return df


def drop_tracking_slots(df: pd.DataFrame) -> pd.DataFrame:
    """Drop all the tracking columns in the specified DataFrame.

    These are columns that specify from which row and file/table each of the output rows was populated
    from. Tracking columns start with the string extra_and_tracking_slots.TRACKING_SLOT_PREFIX and end
    with the string extra_and_tracking_slots.TRACKING_SLOT_SUFFIX.

    Args:
        df (pd.DataFrame): The DataFrame to drop the tracking columns from.

    Returns:
        pd.DataFrame: The copy of df with all the tracking columns dropped.
    """
    drop_cols = [c for c in df.columns if is_tracking_slot(c)]
    df = df.drop(drop_cols, axis=1)
    return df


def add_extra_and_tracking_slot_derivations(
    data: Dict[str, Union[List[Dict], pd.DataFrame]],
    spec: Dict,
    target_schema: SchemaView,
) -> Dict[str, List[str]]:
    """Add slot derivations in the mapping spec to copy over all extra/tracking columns from the source data.

    If there is already a slot derivation for a tracking column then a new slot derivation is NOT added.

    Args:
        data: Dict[str, Union[List[Dict], pd.DataFrame]]: The data that contains the tracking slots that
            we need to copy over. Keys are the source class names, and values are the data. The data are
            either a list of rows (where a row is a dictionary with column names as the keys) or
            a DataFrame, where each column is tested to see if it's a tracking column.
        spec (Dict): The mapper spec to add the slot derivations to, in order to copy over the tracking columns.
            All classes within the spec are processed.
        target_schema (SchemaView): The LinkML schema for the target database that the spec maps onto.

    Returns:
        Dict[str, List[str]]: A dictionary containing all tracking slots that exist in the target data, after mapping
            from the source data. The keys are the target class names and the values are lists of tracking slot names
            that exist in the data if a mapping were to occur.
    """
    tree_root = [
        c for c, defn in target_schema.all_classes().items() if defn.tree_root
    ][0]

    all_extra_slots = get_extra_and_tracking_slots_from_data(data)
    added_extra_slots = {}

    # Go through all classes in the mapper spec
    for target_class_name, class_derivation in spec["class_derivations"].items():
        if "populated_from" not in class_derivation:
            continue
        target_class_name = find_class(
            target_class_name, target_schema, ignore_case=True
        )
        if target_class_name is None:
            continue

        # Get the source class that the class derivation populates from.
        source_class_name = class_derivation["populated_from"]
        if source_class_name == tree_root:
            continue

        # Get all tracking slots that already exist in the class derivation
        existing_extra_slots = [
            c
            for c in class_derivation["slot_derivations"].keys()
            if is_extra_or_tracking_slot(c)
        ]

        # Get all extra/tracking slots that exist in the source data (these will be copied over without modification, specified
        # in the mapper spec)
        source_extra_slots = all_extra_slots.get(source_class_name, [])

        cur_extra_slots = list(dict.fromkeys(existing_extra_slots + source_extra_slots))

        added_extra_slots[target_class_name] = cur_extra_slots

        # Go through all of the tracking slots and add a slot derivation for each of them.
        for col in cur_extra_slots:
            # If a slot derivation already exists then don't add one.
            if col in class_derivation["slot_derivations"]:
                continue
            class_derivation["slot_derivations"][col] = {
                "name": col,
                "populated_from": col,
            }

    return added_extra_slots


def add_extra_and_tracking_slots_to_schema_class(
    extra_and_tracking_slots: List[str], class_name: str, schema: SchemaView
):
    """Add all the specified extra/tracking slots to the class definition for class_name in the schema. They
    will be added to both the top-level list of slots in the schema as well as the class definition
    for class_name in the schema.

    Args:
        extra_and_tracking_slots (List[str]): A list of extra/tracking slot names to add to the class definition in
            the schema.
        class_name (str): The name of the class to add the tracking slots to.
        schema (SchemaView): The schema to add the tracking slots to. The tracking slots are added to
            both the top-level "slots" list and to the class definition for class_name.
    """
    class_definition = schema.schema.classes[class_name]

    # Add all the tracking slots to the class definition, if they don't already exist
    extra_and_tracking_slots = list(
        dict.fromkeys(
            [c for c in extra_and_tracking_slots if c not in class_definition.slots]
        )
    )
    class_definition.slots.extend(extra_and_tracking_slots)

    # Add all the tracking slots to the top-level schema slots
    for slot in extra_and_tracking_slots:
        rng = TrackingSlotsTypes.get(slot, "string")
        schema.schema.slots[slot] = SlotDefinition(
            name=slot, from_schema=schema.schema.id, range=rng
        )


def add_extra_and_tracking_slots_to_schema(
    data: Dict[str, Union[List[Dict], pd.DataFrame]], schema: SchemaView
):
    """Add all extra/tracking slots found in the data to all classes in the schema.

    Tracking slots include the source row number and class name of a row. These get copied over
    to the mapped data so we know which class and row and output row was derived from. It can
    be used for sorting and other downstream operations, such as for ID generation. Extra slots are
    just additional slots that are not found in the original schema that follow a certain naming pattern.
    All of the extra and tracking slots will result in is_extra_or_tracking_slot returning True.

    Args:
        data (Dict[str, Union[List[Dict], pd.DataFrame]]): The data that contains the tracking slots that
            we need to add to the schema. Keys are the source class names, and values are the data. The data are
            either a list of rows (where a row is a dictionary with column names as the keys) or
            a DataFrame, where each column is tested to see if it's a tracking column.
        schema (SchemaView): The schema to add the tracking slots to (for all classes).
    """
    # Get all the extra/tracking slots for each class in the data. all_extra_slots is a dictionary where
    # the keys are the class names in the data and the values are lists of strings (of extra/tracking slot names)
    all_extra_slots = get_extra_and_tracking_slots_from_data(data)

    all_classes = all_classes_without_tree_root(schema)

    # Go through all extra/tracking slots for each class, and add them to the schema.
    for class_name, extra_slots in all_extra_slots.items():
        if class_name not in all_classes:
            continue
        add_extra_and_tracking_slots_to_schema_class(extra_slots, class_name, schema)


def get_extra_and_tracking_slots_from_data(
    data: Dict[str, Union[List[Dict], pd.DataFrame]],
) -> Dict[str, List[str]]:
    """Get a list of all extra/tracking slots found in the data, for all classes. Extra/tracking slots are any
    slot that is_extra_or_tracking_slot(slot) returns True for.

    Args:
        data (Dict[str, Union[List[Dict], pd.DataFrame]]): The data to get the extra/tracking slots from. Keys are
            the source class names, and values are the data. The data are either a list of rows (where a row
            is a dictionary with column names as the keys) or a DataFrame, where each column is tested to see
            if it's an extra/tracking column.

    Returns:
        Dict[str, List[str]]: A dictionary where the keys are the class names and the values are lists of strings,
            where each string is the name of an extra/tracking slot found in the data.
    """
    extra_slots = {}

    # Go through all classes in the data, and find all extra/tracking slots in the data for the class.
    for class_name, class_data in data.items():
        if len(class_data) == 0:
            continue
        if isinstance(class_data, pd.DataFrame):
            extra_slots[class_name] = [
                c for c in class_data.columns if is_extra_or_tracking_slot(c)
            ]
        else:
            extra_slots[class_name] = [
                c for c in class_data[0].keys() if is_extra_or_tracking_slot(c)
            ]
    return extra_slots


def get_tracking_slots() -> List[str]:
    """Get all the predefined tracking slots, which are all the columns specified in TrackingSlots.

    Returns:
        List[str]: List of all predefined tracking slots.
    """
    return [
        getattr(TrackingSlots, v) for v in vars(TrackingSlots) if not v.startswith("__")
    ]


def add_source_tracking_columns(
    df: pd.DataFrame, class_name: str, file: Union[str, Path]
):
    """Add the source tracking columns and values to the DataFrame. These columns specify the source class,
    source file, and source file row that each row in the DataFrame belongs to. The source row
    is 0-based and is equal to the row number in the DataFrame.

    Args:
        df (pd.DataFrame): The DataFrame to add the source tracking columns and values to.
        class_name (str): The value to use for the source class (TrackingSlots.SOURCE_CLASS).
        file (Union[str, Path]): The vaue to use for the source file (TrackingSlots.SOURCE_FILE)

    Raises:
        ValueError: Raised if any of the predefined tracking column already exists in the DataFrame.
    """
    # First make sure the predefined tracking columns don't already exist (this would be due to a name
    # conflict, where the source data already has columns with the same name as a tracking
    # column)
    tracking_slots = get_tracking_slots()
    existing_tracking_slots = [c for c in df.columns if c in tracking_slots]
    if len(existing_tracking_slots) > 0:
        raise ValueError(
            f"Loaded data already has one or more columns with the same name as a tracking column: {existing_tracking_slots}"
        )

    # Add the source tracking columns
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


def load_data_with_source_tracking_columns(
    data_files: Dict[str, List[Union[str, Path, Dict[str, str]]]],
    schema: Union[SchemaView, str, Path] = None,
    max_rows: Optional[int] = 0,
    progress_barid: Optional[str] = None,
    validate_class_names: bool = False,
    validate_columns: bool = False,
) -> Dict[str, List[pd.DataFrame]]:
    """Load all data from disk (as DataFrames) and add the tracking columns that specify which source rows and
    files the data was loaded from.

    Args:
        data_files (Dict[str, List[Union[str, Path, Dict[str, str]]]]): Dictionary of all files to load. The
            keys are the class names and the values are lists of files belonging to that class or dictionaries
            specifying an Excel file and a sheet, in the form
            { EXCEL_FILE_KEY: "file.xlsx", EXCEL_SHEET_KEY: "sheet_name" }.
        schema (Union[SchemaView, str, Path], optional): The source schema that contains the classes that the data_files
            should belong to. Only files belonging to recognized classes are loaded. Defaults to None.
        max_rows (Optional[int], optional): Maximum number of rows to load from each file. If 0 or None then all
            rows are loaded. Defaults to 0.
        progress_barid (Optional[str], optional): If True then show a progress bar with this as its title to show loading
            progress. If None then no progress bar is shown. Defaults to None.
        validate_class_names (bool, optional): If True, then make sure all class names in data_files is
            a valid class name in the schema. If a class name is invalid then a CleanExitError exception is
            raised. Defaults to False.
        validate_columns (bool, optional): If True then check for missing or unrecognized columns in the
            data based on the schema. Unlike validate_class_names, no exception is raised for missing
            or unrecognized columns. Instead log warnings are output. Defaults to False.

    Returns:
        Dict[str, List[pd.DataFrame]]: Keys are the class names (matching the keys in data_file) and the
            values are lists of loaded DataFrames for the class with source tracking columns added.
    """

    """Load all data from disk (as DataFrames) and add the tracking columns that specify which source rows and
    files the data was loaded from.

    Args:
        data_files (Dict[str, List[Union[str, Path, Dict[str, str]]]]): Dictionary of all files to load. The
            keys are the class names and the values are lists of files belonging to that class or dictionaries
            specifying an Excel file and a sheet, in the form
            { EXCEL_FILE_KEY: "file.xlsx", EXCEL_SHEET_KEY: "sheet_name" }.
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
        schema_caster = SchemaCaster(schema)
    else:
        recognized_classes = None
        schema_caster = None

    # Check for invalid class names for the data_files (ie. check the keys of data_files dictionary)
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

    # Create the progress bar
    total_items = sum([len(d) for d in data_files.values()])
    if progress_barid:
        progress = ProgressCounter({progress_barid: total_items}, multiple_bars=False)
    else:
        progress = EmptyCounter()

    warning_log = []
    with progress:
        data_frames = {}
        # Load all data files for each class_name in data_files.
        for class_name, files in data_files.items():
            # Make sure the class_name is valid if validate_class_names is True. This test
            # is not required since we threw an exception above if an invalid class name is found.
            # It is only included here as an extra precaution.
            if (
                validate_class_names
                and recognized_classes is not None
                and class_name not in recognized_classes
            ):
                # Unrecognized class name, so ignore the file (but tell the user)
                for file in files:
                    logger.info(
                        f"Ignoring file from unrecognized table '{class_name}': {file}"
                    )
                    progress.update(progress_barid, 1)
                continue

            if class_name not in data_frames:
                data_frames[class_name] = []

            # Load all the files one at a time
            for file in files:
                try:
                    # Construct track_file, which specifies the source file name. If
                    # the current file is a dictionary, then it has keys that specify
                    # the file name plus other data such as the Excel sheet name for Excel
                    # files. For those types of files we collapse all keys and values
                    # into the file name.
                    if isinstance(file, Dict):
                        params = "&".join(
                            [f"{k}={v}" for k, v in file.items() if k != EXCEL_FILE_KEY]
                        )
                        track_file = f"{file[EXCEL_FILE_KEY]}?{params}"
                    else:
                        track_file = file

                    # Read the data file
                    read_kwargs = {
                        "nrows": max_rows if max_rows else None,
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
                    # Check for missing or unrecognized columns if requested.
                    if validate_columns and schema is not None:
                        new_log = validate_columns_with_schema(
                            df.columns,
                            schema=schema,
                            class_name=class_name,
                            file=track_file,
                            show_log=False,
                        )
                        warning_log.extend(new_log)

                    if schema_caster is not None:
                        schema_caster.cast_df(df, class_name)

                    # Add the predefined source tracking columns
                    add_source_tracking_columns(df, class_name, track_file)

                    data_frames[class_name].append(df)

                    logger.info(
                        f"Loaded {len(df)} rows for table '{class_name}': {track_file}"
                    )

                progress.update(progress_barid, 1)

    # Show warning log messages if there are any. These are messages from checking for
    # unrecognized or missing columns in the loaded data (if validate_columns is True)
    if warning_log:
        for msg in warning_log:
            logger.warning(msg)

    # Raise an exception if no data was loaded.
    if len(data_frames) == 0:
        tables = ", ".join(sorted(recognized_classes))
        msg = f"No recognized tables loaded. Allowable tables are: {tables}"
        raise CleanExitError(msg)

    return data_frames
