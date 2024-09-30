# %%
"""
# ID Generator

Generate IDs in database tables and columns. The ID generator can also be used to generate non-ID values (eg. to parse date/time/timezone into properly formatted strings).

See [/id_generator.md](/id_generator.md) for details.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import Any, List, Dict, Union, Optional, Tuple
from collections.abc import Iterable
import yaml
from pathlib import Path
import pandas as pd
from datetime import datetime
from tqdm import tqdm
from asteval import Interpreter
import argparse
import numpy as np
import traceback
import bisect

from utils.general_utils import (
    read_data_frame,
    save_data_frame,
    get_logger,
    clear_dirs,
)
from utils.cli_utils import get_input_data_files
from id_generator.id_function_bindings import FunctionBindings
from id_generator.id_data_bindings import DataBindings

logger = get_logger(__name__)

# We save the original ID values in the loaded DataFrames to new columns with the same column
# name as the original preceded by ORIG_ID_PREFIX (ie. f"{ORIG_ID_PREFIX}{column_name}")
ORIG_ID_PREFIX = "__"

UNINDEXED_PK_SLOT = f"{ORIG_ID_PREFIX*2}pk_unindexed"
PK_INDEX_SLOT = f"{ORIG_ID_PREFIX*2}pk_index"

# In debug mode, instead of dropping rows with duplicate primary IDs (except for the first duplicate),
# we retain all rows and add a column named DROP_COLUMN which is True if the row would have been dropped
# if not in debug mode.
DROP_COLUMN = "__drop"


class TrackingSlots:
    SOURCE_CLASS = "(__source_class__)"
    SOURCE_ROW = "(__source_row__)"
    SOURCE_FILE = "(__source_file__)"
    SOURCE_FILE_AND_ROW = "(__source_file_and_row__)"


# All columns that should be in the ID code generation config file
class IDCodeColumns:
    CLASS = "class"
    SLOT = "slot"
    # The code columns are in the format f"{CODE_PREFIX}{CODE_SUFFIX}".format(idx), eg "code000", "code001", etc
    CODE_PREFIX = "code"
    CODE_SUFFIX = "{:03d}"


# Keys for linkage paths. These are used in the config file under the ConfigKeys.CLASS_LINKAGES key.
class LinkageKeys:
    SOURCE_CLASS = "source_class"
    SOURCE_SLOT = "source_slot"
    TARGET_CLASS = "target_class"
    TARGET_SLOT = "target_slot"


# Keys for IDGenerator.class_info dictionary, where the tables and related information is stored for each of the
# classes that we are generated IDs for.
class ClassInfoKeys:
    DATA = "data"
    COLUMNS = "columns"
    ORIG_COLUMNS = "orig_columns"
    ROW_INDEX_LOOKUP = "upks_lookup"


# We will create a fast lookup table for any column specified in MAKE_ROW_INDEX_LOOKUPS.
# The keys in MAKE_ROW_INDEX_LOOKUPS are the class name's, and the values are lists of slots
# within the class that should have a fast lookup table.
# The key "*" specifies that the list of slots applies to ALL classes.
# The lookups will be at self.class_info[class_name][ClassInfoKeys.ROW_INDEX_LOOKUP][slot_name]
# and will be a dictionary where the key is the value for the slot and the value is an
# array of row indices into the table. This allows fast searching to retrieve all row indices
# where the row has a specific value in the slot. For example,
# self.class_info[class_name][ClassInfoKeys.ROW_INDEX_LOOKUP][slot]["myValue"] will return
# all row indices in the table class_name where the slot is equal to "myValue". If the key
# "myValue" does not exist then none of the rows match.
MAKE_ROW_INDEX_LOOKUPS = {
    "*": [UNINDEXED_PK_SLOT, TrackingSlots.SOURCE_FILE_AND_ROW],
}


# Keys found in the config file
class ConfigKeys:
    PRIMARY_KEYS = "primary_keys"
    CLASS_LINKAGES = "class_linkages"


class IDGenerator(object):
    def __init__(
        self,
        data_files: Dict[str, List[Union[str, Path]]],
        config_file: str,
        id_code_file: str,
        id_code_sheet: str = None,
    ):
        """Constructor for IDGenerator.

        Args:
            data_files (Dict[str, List[Union[str, Path]]]): All input data files to load for adding IDs to. The keys are the class name and the
                values are lists of files belonging to that class. These can be CSV, TSV, TXT, YAML, or YML files.
            config_file (str): The configuration file.
            id_code_file (str): The tabular file containing the ID generation code for each class/slot that represents
                an ID to be generated. Can be an XLSX, CSV, TSV, TXT, YAML, or YML file. If an Excel file then
                id_code_sheet should also be set.
            id_code_sheet (str, optional): If id_code_file is an Excel file, then the sheet name to load that contains
                the ID generation code. Defaults to None.
        """
        self.config = {}
        if config_file:
            with open(config_file, "r") as f:
                self.config = yaml.safe_load(f)

        # Load all data from disk
        self.load_all(data_files)

        # Prepare the code for calculating IDs
        self.prepare_id_code(id_code_file, id_code_sheet)

        # Prepare the IDs in the loaded DataFrames based on the ID code
        self.prepare_ids()

        # Prepare the config file
        self.prepare_config(config_file)

        # Once everything is loaded finalize the class info and data
        self.finalize_class_info_and_data()

        # Initialize lookup tables
        self.init_lookup_tables()

        # Create the bindings (function and data bindings)
        self.create_bindings()

        # Create the interpreter for executing Python code (the code is in the form of strings)
        self.interpreter = Interpreter(usersyms=self.bindings)

    def is_lookup_slot(self, class_name: str, slot: str) -> bool:
        """Determine if the specified slot has a fast lookup table for accessing the index of rows
        that have a specific value in the slot.

        Args:
            class_name (str): The class name.
            slot (str): The slot within the class.

        Returns:
            bool: True if the slot has a lookup table, False otherwise.
        """
        return slot in self.class_info[class_name][ClassInfoKeys.ROW_INDEX_LOOKUP]

    def get_all_tracking_slots(self) -> List[str]:
        """Get all the tracking slots, which are all the columns specified in TrackingSlots.

        Tracking slots include the source row number and class name of a row. These get copied over
        to the mapped data so we know which class and row and output row was derived from. It can
        be used for sorting and other downstream operations, such as for ID generation.

        Returns:
            List[str]: List of all tracking slots.
        """
        return [
            getattr(TrackingSlots, v)
            for v in vars(TrackingSlots)
            if not v.startswith("__")
        ]

    def init_lookup_tables(self):
        for class_name in self.class_info.keys():
            # Set any other keys
            class_lookup_slots = MAKE_ROW_INDEX_LOOKUPS.get(class_name, [])
            star_lookup_slots = MAKE_ROW_INDEX_LOOKUPS.get("*", [])

            lookup_slots = list(set(class_lookup_slots + star_lookup_slots))
            lookups = {s: {} for s in lookup_slots}

            data = self.class_info[class_name][ClassInfoKeys.DATA]
            for idx in range(len(data)):
                for slot in lookups.keys():
                    row = data[idx, :]
                    val = row[self.get_column_index(class_name, slot)]
                    slot_lookup = lookups.get(slot, {})
                    if val is not None:
                        indices = slot_lookup.get(val, [])
                        indices.append(idx)
                        slot_lookup[val] = indices
                        lookups[slot] = slot_lookup

            self.class_info[class_name][ClassInfoKeys.ROW_INDEX_LOOKUP] = lookups

    def load_all(self, data_files: Dict[str, List[Union[str, Path]]]):
        """Load all data from disk.

        Args:
            data_files (Dict[str, List[Union[str, Path]]]): All data files to load for adding IDs to.
                Keys are the class names and values are lists of files belonging to the class.
        """
        all_tracking_slots = self.get_all_tracking_slots()
        self.class_info = {}
        for class_name, files in data_files.items():
            for file in files:
                logger.info(f"Loading data from {str(file)}")
                self.class_info[class_name] = {}
                df = read_data_frame(file)

                self.class_info[class_name][ClassInfoKeys.DATA] = df

                # Create a list of all original columns found in the dataset (without the tracking slots)
                columns = list(df.columns)
                for s in all_tracking_slots:
                    if s not in columns:
                        raise ValueError(
                            f"Tracking column '{s}' must exist in the data at {str(file)}"
                        )
                    columns.remove(s)
                self.class_info[class_name][ClassInfoKeys.ORIG_COLUMNS] = columns

    def create_bindings(self):
        """Create the function and data bindings. Should be called once all data has been loaded
        and finalized.
        """
        # Get all recognized classes
        class_linkages = self.config.get(ConfigKeys.CLASS_LINKAGES, {})
        primary_keys = self.config.get(ConfigKeys.PRIMARY_KEYS, {})
        all_classes = list(class_linkages.keys())
        all_classes += [
            class_name for lnk in class_linkages.values() for class_name in lnk.keys()
        ]
        all_classes += list(primary_keys.keys())
        all_classes = list(dict.fromkeys(all_classes))

        self.bindings = {
            "dat": DataBindings(
                self,
                root_class="",
                sub_class_names=all_classes,
                replace_empty_values=False,
            ),
            # Same as dat, but if a value is empty then automatically convert it to id_data_bindings.EMPTY_VALUE
            "datEmpty": DataBindings(
                self,
                root_class="",
                sub_class_names=all_classes,
                replace_empty_values=True,
            ),
            "fn": FunctionBindings(self),
        }

    def finalize_class_info_and_data(self):
        """Do some final initialization of the class info and loaded class data. Should be called once
        all data and configurations have been loaded.
        """
        for info in self.class_info.values():
            df = info[ClassInfoKeys.DATA]

            # Add the primary key slot
            df[UNINDEXED_PK_SLOT] = None
            df[PK_INDEX_SLOT] = None
            info[ClassInfoKeys.COLUMNS] = list(df.columns)

            # Convert the DataFrame to a Numpy array
            info[ClassInfoKeys.DATA] = info[ClassInfoKeys.DATA].to_numpy()

    def prepare_config(self, config: str):
        """Load and prepare the configuration file for the ID generator.

        Args:
            config (str): Path to the configuration file.

        Raises:
            ValueError: There is an error in the configuration file.
        """

        # Clean up class_linkages by adding any missing values, and replacing generated ID slots with the slot name
        # with two preceding underlines. If the class_linkages are not specified, then all linkages are
        # performed between classes by matching the TrackingSlots SOURCE_ROW and SOURCE_FILE columns.
        if self.config.get(ConfigKeys.CLASS_LINKAGES, None):
            for source_class, target_linkages in self.config[
                ConfigKeys.CLASS_LINKAGES
            ].items():
                for target_class, linkages in target_linkages.items():
                    self.cleanup_linkage_path(source_class, target_class, linkages)

    def cleanup_linkage_path(
        self, source_class: str, target_class: str, linkages: Union[Dict, List[Dict]]
    ):
        """Cleanup the linkage path(s) by adding any missing (inferred) values along the path.

        A linkage path tells us how to link a row from one class (the source_class) to row(s) in a target class
        (the target_class), by matching slots between classes. For example, to link from a class named "measures"
        to a class named "samples", we might match by "sampleID", in which case the path is:

            source_class: measures
            source_slot: sampleID
            target_class: samples
            target_slot: sampleID

        Linkage paths can be a list of dictionaries instead of a single dictionary, in which case we link from
        the first item in the list to the last item in the list by following each successive linkage path.

        We infer that the first item in the linkage path starts at source_class and the last item in the
        path ends at target_class. Along the path, the source class of the current path item is the target
        class of the previous path item.

        Args:
            source_class (str): The source class that we link from.
            target_class (str): The target class that we link to.
            linkages (Union[Dict, List[Dict]]): A single linkage path item or a list of linkage path items
                that we follow in order.
        """

        def _make_orig(class_name: str, slots: Union[str, List[str]]) -> str:
            if isinstance(slots, str):
                slots = [slots]
            for idx, s in enumerate(slots):
                if self.is_id_generated_slot(class_name, s):
                    slots[idx] = f"{ORIG_ID_PREFIX}{s}"
            return slots

        if not isinstance(linkages, list):
            linkages = [linkages]
        prev_class = source_class
        for idx, linkage in enumerate(linkages):
            # Add SOURCE_CLASS and TARGET_CLASS if they aren't set
            if LinkageKeys.SOURCE_CLASS not in linkage:
                linkage[LinkageKeys.SOURCE_CLASS] = prev_class
            if LinkageKeys.TARGET_CLASS not in linkage:
                # We can only infer that the last item has a TARGET_CLASS equal to target_class.
                # Any item before the last item must have TARGET_CLASS explicitly set.
                if idx < len(linkages) - 1:
                    raise ValueError(
                        f"Error in configuration for class linkages, from class '{source_class}' to class '{target_class}': A target_class must be specified for all but the last linkage in the linkage steps."
                    )
                linkage[LinkageKeys.TARGET_CLASS] = target_class

            # Rename the SOURCE_SLOT and TARGET_SLOT so that they point to the columns where the original
            # IDs are contained. These original slots will remain unchanged. For example, we rename the
            # slot datasetID to {ORIG_ID_PREFIX}datasetID. datasetID will contain the newly calculated ID
            # whereas {ORIG_ID_PREFIX}datasetID will always contain the original unmodified ID.
            linkage[LinkageKeys.SOURCE_SLOT] = _make_orig(
                source_class, linkage[LinkageKeys.SOURCE_SLOT]
            )
            linkage[LinkageKeys.TARGET_SLOT] = _make_orig(
                target_class, linkage[LinkageKeys.TARGET_SLOT]
            )

            prev_class = linkage[LinkageKeys.TARGET_CLASS]

    def prepare_id_code(self, id_code_file: str, id_code_sheet: Optional[str] = None):
        """Load and prepare the ID generation code from the specified file. The file should contain all the
        columns found in IDCodeColumns.

        Args:
            id_code_file (str): The XLSX, CSV, TSV, YAML, YML, or TXT file containing the ID generation code. If an Excel file we
                load the sheet named id_code_sheet.
            id_code_sheet (Optional[str], Optional): If id_code_file is an Excel file, then this is the sheet name to load. If None
                then the first sheet is loaded.
        """
        self.class_ids = {}
        self.id_code_df = pd.DataFrame()
        if not id_code_file:
            return

        if os.path.splitext(id_code_file)[1].lower() == ".xlsx":
            id_code_df = pd.read_excel(
                id_code_file, id_code_sheet if id_code_sheet else 0
            )
        else:
            id_code_df = read_data_frame(id_code_file)

        # id_code_df = id_code_df[id_code_df["class"].isin(["measures"])]

        # Rename any column that starts with the word "code", so that they're in the form "code000" (maintaining the
        # original order)
        code_columns = [
            c for c in id_code_df.columns if c.startswith(IDCodeColumns.CODE_PREFIX)
        ]
        code_columns_map = {
            c: self.make_code_column_name(idx) for idx, c in enumerate(code_columns)
        }
        id_code_df.columns = [code_columns_map.get(c, c) for c in id_code_df.columns]

        # Drop code columns where either the class or slot are empty, or where all code columns are empty
        id_code_df = id_code_df.dropna(
            subset=[IDCodeColumns.CLASS, IDCodeColumns.SLOT], axis=0, how="any"
        )
        id_code_df = id_code_df.dropna(
            subset=code_columns_map.values(), axis=0, how="all"
        )
        self.id_code_df = id_code_df

        # Determine all the ID slots that need to be calculated (in all classes).
        for _, row in self.id_code_df.iterrows():
            class_name = row[IDCodeColumns.CLASS]
            slot = row[IDCodeColumns.SLOT]
            if class_name not in self.class_ids:
                self.class_ids[class_name] = []
            if slot not in self.class_ids[class_name]:
                self.class_ids[class_name].append(slot)

    def prepare_ids(self, regenerate_all_ids: bool = True):
        """Do some preparation of the ID columns in the loaded DataFrames.

        We will copy the IDs to new columns where the names are preceded by ORIG_ID_PREFIX. The values
        in the new columns will remain unchanged, but the values in the old columns will be set to None and
        their IDs generated once make_all_ids is called.

        Args:
            regenerate_all_ids (bool, Optional): If True, then clear all IDs in the input data so that
                we will regenerate all IDs. If False then we do not clear all IDs, and will generate only the
                IDs that are blank. Defaults to True.
        """
        self.current_class = None
        self.current_row_index = None

        for class_name, info in self.class_info.items():
            if class_name not in self.class_ids:
                continue
            logger.info(f"Preparing IDs for class '{class_name}'")
            # Copy all ID columns to new columns preceded by ORIG_ID_PREFIX (eg. __), and clear the
            # original column. Once make_all_ids is called, if the original column has a None value
            # then that means we need to calculate the ID for that column (while the double-underscore
            # column remains unchanged).
            df = info[ClassInfoKeys.DATA]
            slots = self.class_ids[class_name]
            slots = [s for s in slots if s in df.columns]
            if len(slots) == 0:
                continue
            orig_values_slots = [f"{ORIG_ID_PREFIX}{s}" for s in slots]
            df[orig_values_slots] = df[slots]
            if regenerate_all_ids:
                df[slots] = None
            else:
                df[slots] = df[slots].map(
                    lambda x: None if (pd.isna(x) or x == "") else x
                )

    def make_all_ids(
        self,
        class_names: Optional[Union[str, List[str]]] = None,
        row_indices: Optional[Union[int, List[int]]] = None,
    ):
        """Make all IDs that need to be generated.

        Depending on the parameters, this can be either all IDs in all classes, or all IDs in a subset of
        classes and/or a subset of row indices.

        If an ID is non-null, then it has already been generated and will not be re-generated.

        Args:
            class_names (Optional[Union[str, List[str]]], optional): The class names to generate all IDs for. If None then
                all known classes are used. Defaults to None.
            row_indices (Optional[Union[int, List[int]]], optional): The row index or array of row indices to generate
                the IDs for. If None then all rows in all specified classes are generated. Defaults to None.

        Raises:
            ValueError: A slot was specified in the ID code config file that does not exist in the loaded data for
                the class.
        """
        tic = datetime.now()
        orig_row_indices = row_indices

        # We only output progress information if all classes and all row indices are being generated.
        # This is the top-level call to make_all_ids and should only occur once.
        output_progress = class_names is None and row_indices is None

        def _log_info(s: str):
            if output_progress:
                logger.info(s)

        _log_info("Making all IDs...")

        # Get the current class and current row index that we are generating for. We will restore these
        # values once we're done with this function call. This will allow make_all_ids to be called
        # recursively, each with their own current_class and current_row_index.
        orig_current_class = self.current_class
        orig_current_row_index = self.current_row_index

        # Get all the class names to make IDs for
        if class_names is None:
            class_names = list(self.class_info.keys())
        elif isinstance(class_names, str):
            class_names = [class_names]

        # Total number of ID cells to generate. This is to report progress.
        total_ids = np.sum(
            [
                len(self.class_info[c][ClassInfoKeys.DATA])
                * len(self.class_ids.get(c, []))
                for c in class_names
            ]
        )
        processed_ids = 0

        for idx, class_name in enumerate(class_names):
            _log_info(
                f"Making IDs for class '{class_name}' ({idx+1}/{len(class_names)})"
            )

            # All the slots in the class that are IDs that need to be generated
            all_slots = self.class_ids.get(class_name, [])

            # Determine the rows to iterate over (based on row_indices parameter)
            row_indices = orig_row_indices
            if row_indices is None:
                # Generate IDs for all rows
                row_indices = range(
                    0, len(self.class_info[class_name][ClassInfoKeys.DATA])
                )
            else:
                # Only generate IDs for the rows in row_indices. Make sure it's an array.
                if not isinstance(row_indices, Iterable):
                    row_indices = [row_indices]

            # Iterate over all rows to generate the IDs
            processed_indices = 0  # For progress tracking
            for idx in tqdm(row_indices) if output_progress else row_indices:
                processed_indices += 1
                # Iterate over all slots to generate an ID for in the current row
                for slot in all_slots:
                    processed_ids += 1
                    if output_progress:
                        current_progress = processed_indices / len(row_indices) * 100
                        self.report_progress(
                            processed_ids,
                            total_ids,
                            f" (Current={processed_indices}/{len(row_indices)}, {current_progress:0.1f}%)",
                        )

                    # _log_info(f"Making slot '{slot}' in class '{class_name}'")
                    if slot not in self.class_info[class_name][ClassInfoKeys.COLUMNS]:
                        raise ValueError(
                            f"Found slot '{slot}' in class '{class_name}' in ID code file that does not exist in the source data."
                        )

                    # Get the current value for the ID in the data. If it is non-null then it has already been
                    # generated and we can continue to the next loop.
                    v = self.class_info[class_name][ClassInfoKeys.DATA][
                        idx, self.get_column_index(class_name, slot)
                    ]
                    if not pd.isna(v):
                        continue

                    # Calculate the ID
                    self.current_class = class_name
                    self.current_row_index = idx
                    self.calculate_id(class_name, slot, idx)

        # Restore current_class and current_row_index in case make_all_ids has been called recursively
        self.current_class = orig_current_class
        self.current_row_index = orig_current_row_index

        _log_info(f"Finished making all IDs: {datetime.now() - tic}")

    def is_id_generated_slot(self, class_name: str, slot: str) -> bool:
        """Determine if the slot in the class is for an ID that gets generated.

        Args:
            class_name (str): The class of the slot.
            slot (str): The slot.

        Returns:
            bool: True if the slot gets its ID generated, False if it doesn't.
        """
        return class_name in self.class_ids and slot in self.class_ids[class_name]

    def make_code_column_name(self, idx: int) -> str:
        """Get the name of the code column at the specified index in the ID code generation config table.
        The index is 0-based.

        The returned column name might not exist in the code DataFrame (self.id_code_df). The caller
        should make sure the column exists before accessing it.

        Args:
            idx (int): The code index to get the column name for.

        Returns:
            str: The name of the code column at index idx.
        """
        return "{}{}".format(
            IDCodeColumns.CODE_PREFIX, IDCodeColumns.CODE_SUFFIX
        ).format(idx)

    def get_code(self, class_name: str, slot: str, idx: int) -> Optional[str]:
        """Get the ID code for generating the ID for the specified slot.

        Args:
            class_name (str): The class the slot belongs to.
            slot (str): The slot to get the code for.
            idx (int): The code index to use. There may be multiple code columns in the ID code config
                file. We should execute the code starting with the first index (index 0). If the code
                results in an empty value, we should advance to the next code index, and continue until
                a non-empty value is obtained, or we reach a code index where no code is available.

        Returns:
            Optional[str]: The code (at index idx) that generates the ID for the slot. None if no code
                is available.
        """
        # Get the code column name at the index, and make sure the column exists.
        code_column = self.make_code_column_name(idx)
        if code_column not in self.id_code_df.columns:
            return None

        # Filter to get all rows for the specified class and slot.
        code = self.id_code_df[
            (self.id_code_df[IDCodeColumns.CLASS] == class_name)
            & (self.id_code_df[IDCodeColumns.SLOT] == slot)
        ]
        if len(code) == 0:
            return None

        code = code[code_column].iloc[0]
        return code

    def set_data_value(self, class_name: str, slot: str, row_index: int, v: Any):
        """Set the value in the data for the specified class, slot, and row index.

        Args:
            class_name (str): The name of the class.
            slot (str): The slot.
            row_index (int): The row index.
            v (Any): The value to set at the row/slot/class.
        """
        class_info = self.class_info[class_name]

        if self.is_lookup_slot(class_name, slot):
            prev_value = self.get_data_value(class_name, slot, row_index)
            lookup = class_info[ClassInfoKeys.ROW_INDEX_LOOKUP][slot]

            if prev_value != v and prev_value is not None:
                # Remove from previous lookup
                lookup[prev_value].remove(row_index)
            if prev_value != v and v is not None:
                # Add to new lookup
                if v not in lookup:
                    lookup[v] = []
                bisect.insort(lookup[v], row_index)

        class_info[ClassInfoKeys.DATA][
            row_index, self.get_column_index(class_name, slot)
        ] = v

    def get_data_value(self, class_name: str, slot: str, row_index: int) -> Any:
        """Get the value in the data at the specified class, slot, and row index.

        Args:
            class_name (str): The name of the class.
            slot (str): The slot.
            row_index (int): The row index.

        Returns:
            Any: The value at the row/slot/class.
        """
        return self.class_info[class_name][ClassInfoKeys.DATA][
            row_index, self.get_column_index(class_name, slot)
        ]

    def get_column_index(
        self, class_name: str, col: Union[str, List[str]]
    ) -> Union[int, List[int]]:
        """Get the index/indices of the specified column name(s) in the specified class.

        The index is the 0-based column number for the 2D Numpy array for the class. The Numpy array is found
        at self.class_info[class_name][ClassInfoKeys.DATA].

        Args:
            class_name (str): The class name that the column belongs to.
            col (Union[str, List[str]]): The column name(s) to get the index for.

        Returns:
            Union[int, List[int]]: The index or indices for the class name(s).
        """

        def _get_index(c: str) -> int:
            return self.class_info[class_name][ClassInfoKeys.COLUMNS].index(c)

        # col is a single column name (string), return a single index
        if isinstance(col, str):
            return _get_index(col)

        # col is a list of column names, return a list of indices
        indices = []
        for c in col:
            indices.append(_get_index(c))
        return indices

    def get_primary_key(self, class_name: str) -> Optional[str]:
        """Get the primary key for the specified class.

        Args:
            class_name (str): The class (table) name to get the primary key of.

        Returns:
            Optional[str]: The name of the slot that is the primary key for the class. If there is no primary key
                specified in the config file then None is returned.
        """
        if ConfigKeys.PRIMARY_KEYS not in self.config:
            logger.warning(
                f"Key {ConfigKeys.PRIMARY_KEYS} does not exist in config file, assuming no primary keys."
            )
            return None
        return self.config[ConfigKeys.PRIMARY_KEYS].get(class_name, None)

    def is_primary_key(self, class_name: str, slot: str) -> bool:
        """Determine if the slot in the specified class is a primary key for the class.

        Args:
            class_name (str): The class name.
            slot (str): The name of the slot to determine if it is a primary key.

        Returns:
            bool: True if slot is a primary key in the class, False if it is not.
        """
        return slot == self.get_primary_key(class_name)

    def report_progress(self, processed_ids: int, total_ids: int, extra_info: str = ""):
        if processed_ids % 500 == 0:
            # percent_complete = processed_ids / total_ids * 100
            # print(f"Progress: {percent_complete:0.1f}%{extra_info}", end="\r")
            pass

    def get_rows_equal(
        self,
        class_name: str,
        slots: Union[str, List[str]],
        match_value: Any,
        max_rows: Optional[int] = None,
        ignore_indices: Optional[List[int]] = None,
        return_indices: Optional[bool] = False,
    ) -> Union[np.ndarray, Tuple[np.ndarray, np.ndarray]]:
        """Get the rows in class class_name where slots are equal to match_value.

        slots can be either a single slot or a list of slots. For a single slot, if the slot value equals
        match_value or any of the values in match_value (ie. a list of values) then a match occurs.

        For multiple slots, then match_value must either be a list of values, or a list of lists. If a list of
        values (where the values are not lists), then if all elements between the slots and match_values match
        (ie. slots[idx] == match_value[idx] for all idx), then a match occurs. If match_values is a list of lists,
        then if any sublist matches the slots then a match occurs.

        Args:
            class_name (str): The class to get the rows from.
            slots (Union[str, List[str]]): The slot(s) in the class to use for matching.
            match_value (Any): The value(s) to match.
            max_rows (Optional[int], Optional): The maximum number of rows to retrieve. Only the first max_rows matching rows
                are returned. If None then all matched rows are returned. Defaults to None.
            ignore_indices (Optional[List[int]], Optional): A list of indices to ignore. The rows at these indices
                will not be returned. If None then all rows are considered.
            return_indices (Optional[bool], Optional): If True then return the indices of the rows, along with the rows. The return
                value will be the tuple (rows, indices), where indices is a 1-D array of the integer indices of the rows.
                If False then only the rows are returned.

        Returns:
            Union[np.ndarray, Tuple[np.ndarray, np.ndarray]]: If return_indices is False then returns an 2D Numpy array that is
                the selected rows that match. If return_indices is True then returns a tuple consisting of the (rows, indices),
                where indices is a 1D Numpy array specifying the indices of the returned matching rows in the full dataset
                for the class. If no matches are found the either None or the tuple (None, None) are returned,
                depending on the value of return_indices.
        """

        def _ret_value(rows, indices):
            # Create the return value. If return_indices is True we return a tuple (rows, indices), if False we simply return rows
            if return_indices:
                return rows, indices
            return rows

        def _ismatch(v1: Any, v2: Any) -> bool:
            # Test if v1 is equal to v2. We treat all NaNs and "" as equal.
            v1_na = pd.isna(v1) or v1 == ""
            v2_na = pd.isna(v2) or v2 == ""
            return v1 == v2 or (v1_na and v2_na)

        def _row_matches(row: np.ndarray, match_value: Any) -> bool:
            # A row matches if any value in match_value matches
            for cur_match_value in match_value:
                # Make cur_match_value be of the form [a, b, c, ..., n], where n should
                # be equal to the number of slots being matched. If it is not equal to
                # the number of slots then the match for the current value fails.
                if not isinstance(cur_match_value, (list, tuple, np.ndarray)):
                    cur_match_value = [cur_match_value]
                match = True
                if len(cur_match_value) != len(row):
                    match = False
                    break
                # Compare all values in cur_match_value to all values in row. Each value must match
                for m, row_v in zip(cur_match_value, row):
                    if not _ismatch(m, row_v):
                        # No match, so break then continue to the next match_value
                        match = False
                        break
                if match:
                    return True
            return False

        # Get the data and other variables ready
        data = self.class_info[class_name][ClassInfoKeys.DATA]
        if isinstance(slots, str):
            # We are matching a single slot. Make slots an array and
            # also make sure match_value is an array.
            slots = [slots]
            if not isinstance(match_value, (list, tuple, np.ndarray)):
                match_value = [match_value]

        # For finding rows using a slot that has a fast lookup table, use the lookup table
        # @TODO: How to deal with NaNs and ""?
        if len(slots) == 1 and self.is_lookup_slot(class_name, slots[0]):
            all_indices = []
            lookup = self.class_info[class_name][ClassInfoKeys.ROW_INDEX_LOOKUP][
                slots[0]
            ]
            # Find all matches
            for cur_match_value in match_value:
                if not isinstance(cur_match_value, (list, tuple, np.ndarray)):
                    cur_match_value = [cur_match_value]
                for sub_match_value in cur_match_value:
                    if sub_match_value in lookup:
                        indices = lookup[sub_match_value]
                        if ignore_indices is not None:
                            indices = [i for i in indices if i not in ignore_indices]
                        all_indices.append(indices)
            if len(all_indices) == 1:
                return _ret_value(data[all_indices[0]], all_indices[0])
            all_indices = [i for sub in all_indices for i in sub]
            all_indices = list(set(all_indices)).sort()
            if max_rows:
                all_indices = all_indices[:max_rows]

            if len(all_indices) == 0:
                return _ret_value(None, None)
            return _ret_value(data[all_indices], all_indices)

        # Get all matching indices
        matched_indices = []
        slots_idx = self.get_column_index(class_name, slots)
        for idx, row in enumerate(data[:, slots_idx]):
            if ignore_indices is not None and idx in ignore_indices:
                continue
            if _row_matches(row, match_value):
                matched_indices.append(idx)
                if max_rows and len(matched_indices) >= max_rows:
                    break

        if len(matched_indices) == 0:
            return _ret_value(None, None)

        return _ret_value(data[matched_indices], np.array(matched_indices))

    def get_rows_at_index(
        self, class_name: str, index: Union[int, List[int]]
    ) -> np.ndarray:
        """Get the row(s) in the class at the specified indices.

        Args:
            class_name (str): The class to get the rows from.
            index (Union[int, List[int]]): A single index or list of indices to retrieve the
                rows of.

        Returns:
            np.ndarray: The retrieved rows (2D Numpy array).
        """
        if not isinstance(index, Iterable):
            index = [index]
        return self.class_info[class_name][ClassInfoKeys.DATA][index]

    def get_linked_rows(
        self,
        source_class: str,
        source_index: Union[int, List[int]],
        target_class: str,
        max_rows: Optional[int] = None,
        ignore_indices: Optional[List[int]] = None,
        linkage_path: Optional[Union[Dict, List[Dict]]] = None,
        return_indices: Optional[bool] = False,
    ) -> Union[np.ndarray, Tuple[np.ndarray, np.ndarray]]:
        """Get the rows in target_class, that are linked to the row(s) at index source_index in source_class. Use the linkage path to determine
        the linking steps required to go from source_class to target_class. If linkage_path is None then we use the
        linkage path found in the config file (under the ConfigKeys.CLASS_LINKAGES key). Typically, rows in different classes
        are linked by foreign keys and primary keys.

        Args:
            source_class (str): The source class that we are linking from.
            source_index (Union[int, List[int]]): The row index(es) in the source class to link from.
            target_class (str): The target class to get the linked rows from.
            max_rows (Optional[int], Optional): The maximum number of linked rows to retrieve. Only the first max_rows rows
                are returned. If None then all linked rows are returned. Defaults to None.
            ignore_indices (Optional[List[int]], Optional): A list of indices to ignore. The rows at these indices
                will not be returned. If None then all rows are considered.
            linkage_path (Optional[Union[Dict, List[Dict]]], Optional): Configuration of how to link from source_class to target_class. If None then
                the default linkage in the config file is used. Defaults to None.
            return_indices (Optional[bool], Optional): If True then return the indices of all the rows. The return value
                will be a tuple of the form (rows, indices) where indices is a 1-D array of indices for each row. If False
                then only the rows are returned. Defaults to False.

        Returns:
            Union[np.ndarray, Tuple[np.ndarray, np.ndarray]]: If return_indices is False then returns an 2D Numpy array that is
                the linked rows. If return_indices is True then returns a tuple consisting of the (rows, indices),
                where indices is a 1D Numpy array specifying the indices of the returned matching rows in the full dataset
                for the class. If no linked rows are found the either None or the tuple (None, None) are returned,
                depending on the value of return_indices.
        """

        def _ret_value(rows, indices):
            # Create the return value. If return_indices is True we return a tuple (rows, indices), if False we simply return rows
            if return_indices:
                return rows, indices
            return rows

        if source_class not in self.class_info or target_class not in self.class_info:
            return _ret_value(None, None)

        # If the source_class and target_class are the same, then we just return the source row
        # (in class source_class and row source_index)
        if source_class == target_class:
            rows = self.get_rows_at_index(source_class, source_index)
            return _ret_value(rows, [source_index])

        # Load the linkage path that goes from the source_class to target_class, if it was not specified.
        if linkage_path is None:
            linkage_path = self.get_default_linkage_path(source_class, target_class)
        else:
            self.cleanup_linkage_path(source_class, target_class, linkage_path)

        # If no linkage path is available, then return None
        if linkage_path is None:
            raise ValueError(
                f"No linkage path available to link from class '{source_class}:{source_index}' to class '{target_class}'"
            )
            # return _ret_value(None, None)

        if not isinstance(linkage_path, (list, tuple)):
            linkage_path = [linkage_path]

        # Loop through the linkage path to link from the source class (and source index) to the
        # target class. We retrieve all rows in the target class that are linked to rows in the
        # source class.
        cur_class = source_class
        rows = self.get_rows_at_index(source_class, source_index)
        indices = [source_index]
        if rows is None:
            raise ValueError(
                f"No row(s) at index {source_index} in class '{source_class}'"
            )
        for linkage in linkage_path:
            linkage_source_class = linkage[LinkageKeys.SOURCE_CLASS]
            linkage_source_slot = linkage[LinkageKeys.SOURCE_SLOT]
            linkage_target_class = linkage[LinkageKeys.TARGET_CLASS]
            linkage_target_slot = linkage[LinkageKeys.TARGET_SLOT]

            if cur_class != linkage_source_class:
                raise ValueError(
                    f"source_class ('{linkage_source_class}') does not match current class ('{cur_class}') in linkage path from '{source_class}' to '{target_class}'."
                )

            # Get unique rows at the source class and slot(s)
            if not isinstance(linkage_source_slot, (list, tuple, np.ndarray)):
                linkage_source_slot = [linkage_source_slot]
            rows = rows[:, self.get_column_index(source_class, linkage_source_slot)]
            # Get all values to match, obtained from the source table, that we want to match
            # in the target table.
            row_match = tuple(set(map(tuple, rows)))

            rows, indices = self.get_rows_equal(
                linkage_target_class,
                linkage_target_slot,
                row_match,
                max_rows=max_rows,
                ignore_indices=ignore_indices,
                return_indices=True,
            )
            if rows is None or len(rows) == 0:
                return _ret_value(None, None)

            cur_class = linkage_target_class

        return _ret_value(rows, indices)

    def get_first_linked_row(
        self,
        source_class: str,
        source_index: int,
        target_class: str,
        linkage_path: Optional[Union[Dict, List[Dict]]] = None,
        return_index: bool = False,
    ) -> Union[np.ndarray, Tuple[np.ndarray, int]]:
        """Get the first row in target_class that is linked to the row at index source_index in the class source_class.

        Args:
            source_class (str): The source class.
            source_index (int): The row index in the source class that we want to get the linked rows for.
            target_class (str): The target class to get the linked rows from.
            linkage_path (Optional[Union[Dict, List[Dict]]], Optional): The configuration specifying how to link from source_class to target_class. If None
                then the default linkage path from source_class to target_class in the config file is used. Defaults to None.
            return_index (Optional[bool], Optional): If True then return the index of the first linked row, in addition to
                the row. The return value will be the tuple (row, index)

        Returns:
            Union[np.ndarray, Tuple[np.ndarray, int]]: If return_index is False then a 1D Numpy array is returned
                that is the first linked row in the target class. If return_index is True then a tuple of the form
                (row, index) is returned, where index is the index of the row in the full dataset for the target class.
                If no linked rows are found the either None or the tuple (None, None) are returned,
                depending on the value of return_indices.
        """
        rows, indices = self.get_linked_rows(
            source_class,
            source_index,
            target_class,
            max_rows=1,
            linkage_path=linkage_path,
            return_indices=return_index,
        )
        if rows is None or len(rows) == 0:
            row = None
            idx = None
        else:
            row = rows[0]
            idx = indices[0]
        if return_index:
            return row, idx
        else:
            return row

    def get_first_linked_value(
        self,
        source_class: str,
        source_index: int,
        target_class: str,
        target_slot: str,
        linkage_path: Optional[Union[Dict, List[Dict]]] = None,
    ) -> Any:
        """Get the first value in target_class and slot target_slot that is linked to the row in source_class at row index source_index, using
        the linkage_path to determine how to link from source_class to target_class. If linkage_path is None then we use the
        linkage path found in the config file (self.config[ConfigKeys.CLASS_LINKAGES])

        Args:
            source_class (str): The source class we are linking from.
            source_index (int): The row index in the source class to link from.
            target_class (str): The target class that we want to get the linked value from.
            target_slot (str): The slot in the target class to get the value from.
            linkage_path (Optional[Union[Dict, List[Dict]]], Optional): Configuration of how to link from source_class to target_class. If None then
                the default linkage in the config file is used. Defaults to None.

        Returns:
            Any: The first linked value in the target class and slot. If no linked value is found then None is returned.
        """
        row, idx = self.get_first_linked_row(
            source_class, source_index, target_class, linkage_path, return_index=True
        )
        if row is None:
            return None

        # If the target slot is an ID that needs to be generated, then generate it and return the value
        if self.is_id_generated_slot(target_class, target_slot) and pd.isna(
            row[self.get_column_index(target_class, target_slot)]
        ):
            return self.calculate_id(target_class, target_slot, idx)

        return row[self.get_column_index(target_class, target_slot)]

    def get_default_linkage_path(
        self, source_class: str, target_class: str
    ) -> Optional[Union[Dict, List[Dict]]]:
        """Get the default class linkage, that specifies the steps required to link a row in source_class to
        row(s) in target_class. The default linkage is the one specified in the config file under the
        ConfigKeys.CLASS_LINKAGES key.

        Args:
            source_class (str): The source class to link from.
            target_class (str): The target class to link to.

        Returns:
            Optional[Union[Dict, List[Dict]]]: The list of linkage steps (or optionally a dictionary if the linkage path has a
            single step) to go from the source class to target class. The dictionaries are of the form:
                    {
                        source_class: "class1",
                        source_slot: "slot1",
                        target_class: "class2",
                        target_slot: "slot2",
                    }
                In the above example, to go link rows in "class1" to rows in "class2", we extract all rows from "class2"
                where "slot2" is equal to the value found in the source row in "slot1". In some cases, we may need to link
                through multiple classes to get from the source class to the target class. This is specified by having multiple
                dictionaries in the returned list. Returns None if no linkage path from source_class to target_class is available.
        """
        if not self.config.get(ConfigKeys.CLASS_LINKAGES, None):
            # If no class_linkages are specified in the config file, then link by the source file and row
            # tracking column.
            return {
                LinkageKeys.SOURCE_SLOT: TrackingSlots.SOURCE_FILE_AND_ROW,
                LinkageKeys.SOURCE_CLASS: source_class,
                LinkageKeys.TARGET_SLOT: TrackingSlots.SOURCE_FILE_AND_ROW,
                LinkageKeys.TARGET_CLASS: target_class,
            }

        if source_class not in self.config[ConfigKeys.CLASS_LINKAGES]:
            return None
        linkage = self.config[ConfigKeys.CLASS_LINKAGES][source_class]
        return linkage.get(target_class, None)

    def calculate_id(self, class_name: str, slot: str, row_index: int) -> Any:
        """Calculate the ID for the slot in the class at the specified row index. The ID is
        calculated based on the ID generation code for the class/slot combination, and is found
        in the ID code config file.

        Args:
            class_name (str): The class that the slot belongs to.
            slot (str): The slot to calculate the ID for.
            row_index (int): The row index in the class's DataFrame that we calculate the slot for.

        Returns:
            Any: The calculated ID.
        """
        if class_name not in self.class_info:
            return None

        # We loop through all code columns for the slot. Once executing the code generates a
        # non-empty value (either returned from the code or with the "target" variable being set
        # in the code), we use that value as the generated ID and stop looping over the code
        # columns. If we have executed all the code columns and all of them have generated an
        # empty value, we return without setting the ID
        # @TODO: Deal with case where all code columns results in an empty value. May want to set
        # the ID in the Numpy data to an empty string.
        v = None
        code_idx = -1
        while True:
            code_idx += 1
            code = self.get_code(class_name, slot, code_idx)

            if pd.isna(code) or not code:
                v = None
                break

            orig_current_class = self.current_class
            orig_current_row_index = self.current_row_index
            self.current_class = class_name
            self.current_row_index = row_index

            if "target" in self.interpreter.symtable:
                del self.interpreter.symtable["target"]
            try:
                v = self.interpreter(code, raise_errors=True)
            except Exception as e:
                # format_exc() will provide extra traceback information related to the exception that occurred
                # when executing the code string.
                print("*" * 100)
                print(traceback.format_exc())
                print("=" * 100)
                raise ValueError(
                    f"Error when calculating ID for '{class_name}.{slot}:{row_index}': {e}\nCode: {code}"
                )
            finally:
                self.current_class = orig_current_class
                self.current_row_index = orig_current_row_index

            # If the variable "target" has been set by the code, then use that value instead
            if "target" in self.interpreter.symtable:
                v = self.interpreter.symtable["target"]

            # If the code resulted in an empty value, continue to the next code column
            if pd.isna(v) or v == "":
                continue

            break

        if pd.isna(v):
            v = ""

        self.set_data_value(class_name, slot, row_index, v)

        # If the slot is the primary key, then calculate the remainder of the row, so we can determine if the
        # row is a duplicate or not of all other rows generated so far that have the same primary key value.
        # If it is a duplicate, we reuse an existing primary key ID from the duplicates. If it is not
        # a duplicate we make sure the primary key value is unique.
        if self.is_primary_key(class_name, slot):
            self.make_all_ids(class_name, row_index)
            # Grouping the primary keys will either group the new calculated ID with an existing
            # ID where the rows are identical, or will add an index to the end of the new ID
            # if there are no identical rows but the new ID is already in use (ie. we will
            # make the new ID unique)
            self.group_primary_key(class_name, row_index)

        return self.get_data_value(class_name, slot, row_index)

    def group_primary_key(self, class_name: str, row_index: int) -> Any:
        """For the (unindexed) primary key value currently found at the row index in the specified class,
        either group it with other rows generated so far that are identical to the row at row_index
        (by using the same primary key index as found in the duplicate rows), or if there are no other
        identical rows so far add an optional index to make sure the primary key is unique.

        An unindexed primary key value is the original calculated ID, without any modification. These
        values are stored in the UNINDEXED_PK_SLOT of the class's Numpy data. In order to create a unique
        primary key from this unindexed value, we add an index to it (eg. a trailing number).
        This index number is stored in PK_INDEX_SLOT. The actual primary key becomes a combination
        of the unindexed pk value and the pk index (eg. "mySample" + "001" = "mySample001").

        If the pk index is 0 then the indexed pk value will be the same as the unindexed pk value
        (eg. "mySample", without a trailing number).

        When calling this function, the value currently found in the row's primary key column is
        assumed to be the unindexed value. Both the values at PK_INDEX_SLOT and UNINDEXED_PK_SLOT
        are ignored. Once this function is complete, all three of these columns will be set with
        the new values.

        Args:
            class_name (str): The class that contains the row to group.
            row_index (int): The 0-based row number in the class to group the primary key for.

        Returns:
            Any: The value of the primary key at row row_index, after any grouping is performed.
        """

        def _make_indexed_pk(unindexed_pk: str, pk_index: int) -> str:
            """Make an indexed primary key value, based on the unindexed primary key value and
            a numerical index."""
            if pk_index:
                return f"{unindexed_pk}{pk_index:03d}"
            else:
                return unindexed_pk

        def _set_current_row_values(unindexed_pk: str, pk_index: int):
            """Set the ID values for the current row (the indexed pk value in pk_slot, the
            unindexed pk value in UNINDEXED_PK_SLOT, and the index in PK_INDEX_SLOT).
            """
            self.set_data_value(class_name, PK_INDEX_SLOT, row_index, pk_index)
            self.set_data_value(class_name, UNINDEXED_PK_SLOT, row_index, unindexed_pk)
            indexed_pk_value = _make_indexed_pk(unindexed_pk, pk_index)
            self.set_data_value(class_name, pk_slot, row_index, indexed_pk_value)

        pk_slot = self.get_primary_key(class_name)

        # The unindex PK value is currently at pk_slot. Copy the value over to the UNINDEXED_PK_SLOT
        # then clear pk_slot (since we will recalculate it)
        unindexed_pk_value = self.get_data_value(class_name, pk_slot, row_index)
        self.set_data_value(class_name, pk_slot, row_index, None)
        self.set_data_value(class_name, PK_INDEX_SLOT, row_index, None)
        self.set_data_value(
            class_name, UNINDEXED_PK_SLOT, row_index, unindexed_pk_value
        )

        # Get the current row (at row_index)
        current_row = self.get_rows_at_index(class_name, row_index)

        # Get all rows that have the same unindexed primary key value
        # indices = self.class_info[class_name][ClassInfoKeys.ROW_INDEX_LOOKUP][UNINDEXED_PK_SLOT][unindexed_pk_value].copy()
        # indices.remove(row_index)
        # rows = self.class_info[class_name][ClassInfoKeys.DATA][indices]

        rows, indices = self.get_rows_equal(
            class_name,
            UNINDEXED_PK_SLOT,
            unindexed_pk_value,
            ignore_indices=[row_index],
            return_indices=True,
        )

        # if rows is None:
        #     raise RuntimeError(
        #         f"No rows in class '{class_name}' match the unindexed primary key value '{unindexed_pk_value}', at least one must exist."
        #     )

        if rows is None:
            rows = []

        if len(rows) > 0:
            # Get the rows that are identical to current_row
            # The columns we use for matching are all of the original columns in the loaded DataFrame, without the primary key column
            # but with the column at UNINDEXED_PK_SLOT.
            columns = [
                self.get_column_index(class_name, c)
                for c in self.class_info[class_name][ClassInfoKeys.ORIG_COLUMNS]
                if c != pk_slot
            ]
            columns.append(self.get_column_index(class_name, UNINDEXED_PK_SLOT))

            # Replace NANs so that they can be equated to each other (normally, float("nan") == float("nan") is False, but we
            # want it to be true by replacing the nan values with a single comparable value)
            nanobj = object()
            rows_nan = rows[:, columns].copy()
            current_row_nan = current_row[:, columns].copy()
            rows_nan[np.where(pd.isna(rows_nan))] = nanobj
            current_row_nan[np.where(pd.isna(current_row_nan))] = nanobj

            # Collect all rows that are identical to the current row
            identical_rows_filt = np.equal(rows_nan, current_row_nan).all(axis=1)
            identical_rows = rows[identical_rows_filt, :]
        else:
            # There are no identical rows
            identical_rows = []

        if len(identical_rows) > 0:
            # There are identical rows, so use the PK index found in the first identical row
            pk_index = identical_rows[
                0, self.get_column_index(class_name, PK_INDEX_SLOT)
            ]
            _set_current_row_values(unindexed_pk_value, pk_index)
        else:
            # There are no identical rows, so get a PK index that results in a unique indexed PK
            pk_index = 0
            if len(rows) > 0:
                index_values = rows[:, self.get_column_index(class_name, PK_INDEX_SLOT)]
                index_values = index_values[~pd.isna(index_values)]
                if len(index_values) > 0:
                    pk_index = index_values.max() + 1
            while True:
                indexed_pk_value = _make_indexed_pk(unindexed_pk_value, pk_index)
                # If indexed_pk_value is unique in column pk_slot then use it.
                # Note that we have previously set the value in column pk_slot for the current row to None
                if (
                    indexed_pk_value
                    not in self.class_info[class_name][ClassInfoKeys.DATA][
                        :, self.get_column_index(class_name, pk_slot)
                    ]
                ):
                    break
                pk_index += 1
            _set_current_row_values(unindexed_pk_value, pk_index)

        return self.get_data_value(class_name, pk_slot, row_index)

    def get_source_class_and_row(
        self, class_name: str, row_index: int
    ) -> Tuple[Optional[str], Optional[int]]:
        """Get the source class and source row that were used to populate the row at row_index (0-based) of
        the table class_name.

        Args:
            class_name (str): The class name.
            row_index (int): The row index (0-based) in the table for class_name that we want the source class
                and source row of.

        Returns:
            Tuple[Optional[str], Optional[int]]: A tuple of the form ("source_class", source_row), or (None, None)
                if the source class and row could not be retrieved.
        """
        return (
            self.get_data_value(
                self.current_class, TrackingSlots.SOURCE_CLASS, self.current_row_index
            ),
            self.get_data_value(
                self.current_class, TrackingSlots.SOURCE_ROW, self.current_row_index
            ),
        )

    def get_current_source_class_and_row(self) -> Tuple[Optional[str], Optional[int]]:
        """Get the source class and source row that was used to populate the current class and current row.

        Returns:
            Tuple[Optional[str], Optional[int]]: A tuple of the form ("source_class", source_row), or (None, None)
                if the source class and row could not be retrieved.
        """
        return self.get_source_class_and_row(self.current_class, self.current_row_index)

    def save_all(
        self,
        output_dir: str,
        orig_columns_only: bool = True,
        drop_duplicates: bool = True,
    ) -> Dict[str, List[Path]]:
        """Save all DataFrames to disk.

        Args:
            output_dir (str): Directory to save DataFrames to.
            orig_columns_only (bool, optional): If True then only save the original columns that were part
                of the source database and table for all output files. If False then all columns are saved,
                including any columns temporarily created for mapping operations and debugging columns.
                Defaults to True.
            drop_duplicates (bool, optional): If True then drop all rows where the primary key is a duplicate
                (except for the first duplicate). If False then all rows are retained, instead a column named
                DROP_COLUMN is added and set to True if the row would have been dropped. Note that
                the DROP_COLUMN column will only be retained if orig_columns_only is False. Defaults to True.

        Returns:
            Dict[str, List[Path]]: All saved files, where the keys are the target class names and the values
                are lists of output files for the class.
        """
        tic = datetime.now()
        logger.info(f"Saving all data to {output_dir}")
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        output_data_files = {}
        for class_name, info in self.class_info.items():
            data = info[ClassInfoKeys.DATA]
            output_file = os.path.join(output_dir, f"{class_name}.csv")
            data = pd.DataFrame(data, columns=info[ClassInfoKeys.COLUMNS])

            # Drop rows where primary key is a duplicate
            pk_slot = self.get_primary_key(class_name)
            if pk_slot:
                orig_len = len(data)

                if drop_duplicates:
                    # Drop rows where pk_slot is a duplicate
                    data = data.drop_duplicates(pk_slot, keep="first")
                    new_len = len(data)
                else:
                    # Add "drop" column for testing
                    columns = list(data.columns)
                    dupes_filt = data.duplicated(pk_slot, keep="first")
                    data.loc[dupes_filt, DROP_COLUMN] = True
                    data = data[[DROP_COLUMN] + columns]
                    new_len = orig_len - data[DROP_COLUMN].sum()

                logger.info(
                    f"Dropped duplicate primary keys for class '{class_name}': {orig_len} -> {new_len} ({new_len-orig_len})"
                )

            if orig_columns_only:
                # Remove additional columns that were added temporarily for execution purposes
                data = data[info[ClassInfoKeys.ORIG_COLUMNS]]

            save_data_frame(data, output_file, index=False)
            if class_name not in output_data_files:
                output_data_files[class_name] = []
            output_data_files[class_name].append(Path(output_file))
        logger.info(f"Finished saving: {datetime.now() - tic}")
        return output_data_files


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        class opts:
            # NWSS to ODM v2
            input_data_dir = "../../gen/nwss_reporting_to_v2/temp/mapped_data"
            input_data_files = None
            output_dir = "../../gen/nwss_reporting_to_v2/mapped_data_ids"
            id_code_file = "../../data/modules/nwss_reporting_to_v2/ids/nwss_reporting_to_v2_id_code.xlsx"
            id_code_sheet = "id_code"
            config_file = "../../data/modules/nwss_reporting_to_v2/ids/nwss_reporting_to_v2_id_config.yaml"

            # ODM v1 to ODM v2
            # input_data_dir = "../../gen/odm_v1_to_v2/temp/mapped_data"
            # input_data_files = None
            # output_dir = "../../gen/odm_v1_to_v2/mapped_data_ids"
            # id_code_file = "../../data/modules/odm_v1_to_v2/ids/odm_v1_to_v2_id_code.xlsx"
            # id_code_sheet = "id_code"
            # config_file = "../../data/modules/odm_v1_to_v2/ids/odm_v1_to_v2_id_config.yaml"

            debug = True
        # fmt: on
    else:
        args = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
        args.add_argument(
            "--input_data_dir",
            type=str,
            help="Location of all data files to add the IDs to. The file name (without extension) should be the class name. All CSV, TSV, TXT, YAML, and YML files are loaded.",
            required=False,
        )
        args.add_argument(
            "--input_data_files",
            nargs="+",
            type=str,
            help="List of all input data files to add the IDS to, and the source class for each file. Format is 'class_name file.csv [class_name2 file2.csv ...]'",
            required=False,
        )
        args.add_argument(
            "--output_dir",
            type=str,
            help="Directory to save the final data to, in which all IDs have been generated.",
            required=True,
        )
        args.add_argument(
            "--config_file", type=str, help="The YAML config file.", required=True
        )
        args.add_argument(
            "--id_code_file",
            type=str,
            help="The XLSX, CSV, TSV, TXT, YAML, or YML configuration file that contains the ID generation code. If an XLSX file then the sheet named id_code_sheet is loaded.",
            required=True,
        )
        args.add_argument(
            "--id_code_sheet",
            type=str,
            help="If id_code_file is an Excel file, then load the code from the sheet with this name.",
            default=None,
            required=False,
        )
        args.add_argument(
            "--debug",
            action="store_true",
            help="If set then run in debug mode, which only affects what is included in the output data files. Debug data includes some additional columns (eg. original ID values, row number column for linking, primary key index and values, etc.). Debug output will also include any duplicated primary keys, with an additional 'drop' column specifying if it is a duplicate, in which case the row would be dropped when not in debug mode.",
        )
        opts = args.parse_args()

    data_files = get_input_data_files(opts.input_data_files, opts.input_data_dir)

    clear_dirs([opts.output_dir])
    gen = IDGenerator(
        data_files, opts.config_file, opts.id_code_file, opts.id_code_sheet
    )
    gen.make_all_ids()
    gen.save_all(
        opts.output_dir,
        orig_columns_only=not opts.debug,
        drop_duplicates=not opts.debug,
    )
