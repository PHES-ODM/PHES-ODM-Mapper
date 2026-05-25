"""
# ID Generator

Generate IDs in database tables and columns. The ID generator can also be used to generate non-ID values (eg. to parse date/time/timezone into properly formatted strings).

See [/docs/id_generator.md](/docs/id_generator.md) for details.
"""

from typing import Any, List, Dict, Union, Optional, Tuple
import os
import yaml
from collections.abc import Iterable
from pathlib import Path
import pandas as pd
from datetime import datetime
from asteval import Interpreter
import numpy as np
import traceback

from linkml_runtime import SchemaView

from odm_map.utils.logger import get_logger
from odm_map.utils.general_utils import (
    read_data_frame,
    merge_dicts_of_lists,
)
from odm_map.utils.extra_and_tracking_slots import TrackingSlots
from odm_map.progress import ProgressCounter, EmptyCounter
from odm_map.id_generator.id_function_bindings import FunctionBindings
from odm_map.id_generator.id_data_bindings import DataBindings
from odm_map.id_generator.generator_data import (
    GeneratorData,
    IDValue,
    get_slot_and_selectors_from_slot,
    add_code_selector_to_slot,
)
from odm_map.id_generator.id_na import isna, EMPTY_OBJ
from odm_map.id_generator.generator_config_keys import ConfigKeys
from odm_map.utils.schema_utils import all_primary_keys

PREPARING_BARID = "Preparing IDS"
TOTAL_IDS_TITLE = "TOTAL IDs"
FINALIZE_BARID = "Processing Data"

logger = get_logger(__name__)


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


# We will create a fast lookup table for any column specified in MAKE_ROW_INDEX_LOOKUPS.
# The keys in MAKE_ROW_INDEX_LOOKUPS are the class name's, and the values are lists of slots
# within the class that should have a fast lookup table.
# The key "*" specifies that the list of slots applies to ALL classes.
# The lookups will stored in the GeneratorData objects at self.data
MAKE_ROW_INDEX_LOOKUPS = {
    "*": [TrackingSlots.SOURCE_FILE_AND_ROW],
}


class IDGenerator(object):
    def __init__(
        self,
        data_files: Dict[str, List[Union[str, Path]]],
        data_frames: Dict[str, List[pd.DataFrame]],
        schema: Union[str, Path, SchemaView],
        config_file: Union[Union[str, Path, Dict], List[Union[str, Path, Dict]]],
        id_code_files: List[Dict],
        multi_bar_progress: bool = True,
        for_merging: bool = False,
    ):
        """Constructor for IDGenerator.

        Args:
            data_files (Dict[str, List[Union[str, Path]]]): All input data files to load for adding IDs to (in addition to the DataFrames in
                data_frames). The keys are the class name and the values are lists of files belonging to that class. These can be CSV, TSV,
                TXT, YAML, or YML files.
            data_frames (Dict[str, List[pd.DataFrame]]): All input DataFrames that we want to generate IDs for. The keys are the class names
                and the values are lists of DataFrames belonging to the class.
            schema (Union[str, Path, SchemaView]): The path to the LinkML schema that we are generating IDs for.
            config_file (Union[Union[str, Path, Dict], List[Union[str, Path, Dict]]]): The configuration file(s) and/or dictionaries. If
                multiple values are specified then they are merged together. Dictionaries are treated as
                config files that have already been loaded into memory.
            id_code_files (List[Dict]): List of dictionaries specifying the files containing the ID code. The
                dictionaries are in one of the following forms:
                    1) {"id_code_file": "file.xlsx", "id_code_sheet": "sheet"}. id_code_file
                       can be a CSV, TSV, or XLSX file. If an XLSX file then "id_code_sheet" specifies which
                       sheet in the Excel file to use. If "id_code_sheet" is None or missing then the first
                       sheet is used.
                    2) {"id_code_df: df}. df is a pd.DataFrame of the ID code. It is treated the same as a
                       code file that has already been loaded into memory.
            multi_bar_progress (bool, optional): If True then output multiple progress bars at the same time showing all classes we will be
                generating IDs for. If False then only one progress bar is shown at a time (for the class name we are currently
                generating IDs for).
        """
        self.tic = datetime.now()

        if isinstance(schema, (str, Path)):
            schema = SchemaView(schema)
        self.schema = schema

        self.for_merging = for_merging
        self.primary_keys = all_primary_keys(self.schema)

        # Sort data_files by key (class name), and sort all the values (file names)
        # data_files = { k: sorted(v) for k, v in sorted(data_files.items())}

        self.load_configs(config_file)

        self.current_class = None
        self.current_row_index = None
        self.multi_bar_progress = multi_bar_progress

        # Prepare the code for calculating IDs
        self.prepare_id_code(id_code_files)

        # Load all data from disk
        self.load_all(data_files=data_files, data_frames=data_frames)

        # Create the bindings (function and data bindings)
        self.create_bindings()

        # Create the interpreter for executing Python code (the code is in the form of strings)
        self.interpreter = Interpreter(usersyms=self.bindings)
        self.interpreter_clean_symtable = self.interpreter.symtable.copy()

    def load_configs(
        self, config_files: Union[Union[str, Path, Dict], List[Union[str, Path, Dict]]]
    ):
        """Load and merge all the specified configuration file(s) and/or dictionaries.

        The following rules are applied when merging for each key in the config file:

            ConfigKeys.CLASS_LINKAGES: Each dictionary at config[ConfigKeys.CLASS_LINKAGES][class_name]
                gets updated (by calling dict.update) in order of the config files.
            ConfigKeys.NAMED_CLASS_LINKAGES: The top-level dictionary (config[ConfigKeys.NAMED_CLASS_LINKAGES]) gets
                updated (by calling dict.update) in order of the config files. In other words named linkages
                with the same name get replaced.

        Args:
            config_files (Union[Union[str, Path, Dict], List[Union[str, Path, Dict]]]): Path(s) to YAML
                configuration files and/or dictionaries. If dictionaries then they are treated
                as files that have already been loaded into memory. If a list of configurations is
                provided then they are merged together.
        """
        self.config = {}
        if not config_files:
            return

        if not isinstance(config_files, (list, tuple)):
            config_files = [config_files]
        self.config = {}
        for cur_config_file in config_files:
            if isinstance(cur_config_file, dict):
                cur_config = cur_config_file
            else:
                with open(cur_config_file, "r") as f:
                    cur_config = yaml.safe_load(f)
            if not cur_config:
                cur_config = {}

            # Merge class linkages
            if ConfigKeys.CLASS_LINKAGES in cur_config:
                if ConfigKeys.CLASS_LINKAGES not in self.config:
                    self.config[ConfigKeys.CLASS_LINKAGES] = {}
                for key, val in cur_config[ConfigKeys.CLASS_LINKAGES].items():
                    if key not in self.config[ConfigKeys.CLASS_LINKAGES]:
                        self.config[ConfigKeys.CLASS_LINKAGES][key] = {}
                    self.config[ConfigKeys.CLASS_LINKAGES][key].update(val)

            # Merge named class linkages
            if ConfigKeys.NAMED_CLASS_LINKAGES in cur_config:
                if ConfigKeys.NAMED_CLASS_LINKAGES not in self.config:
                    self.config[ConfigKeys.NAMED_CLASS_LINKAGES] = {}
                self.config[ConfigKeys.NAMED_CLASS_LINKAGES].update(
                    cur_config[ConfigKeys.NAMED_CLASS_LINKAGES]
                )

            # Merge table short names
            if ConfigKeys.TABLES_TO_SHORTNAMES in cur_config:
                if ConfigKeys.TABLES_TO_SHORTNAMES not in self.config:
                    self.config[ConfigKeys.TABLES_TO_SHORTNAMES] = {}
                self.config[ConfigKeys.TABLES_TO_SHORTNAMES].update(
                    cur_config[ConfigKeys.TABLES_TO_SHORTNAMES]
                )

    def get_class_lookup_slots(self, class_name: str) -> List[str]:
        def _get_slots_for_class(linkages: Union[Dict, List[Dict]]) -> List[str]:
            """Get all the slots for class_name that are referenced in the linkages.

            Args:
                linkages (Union[Dict, List[Dict]]): The linkages to retrieve the referenced slots
                    from. Dictionaries should have all the LinkageKeys set.

            Raises:
                ValueError: The linkages are not in the correct format.

            Returns:
                List[str]: List of all slots for class_name referenced in the linkages.
            """
            slots = []
            if isinstance(linkages, dict):
                # First get the source_class/source_slot values, then the target_class/target_slot values.
                for class_key, slot_key in [
                    [LinkageKeys.SOURCE_CLASS, LinkageKeys.SOURCE_SLOT],
                    [LinkageKeys.TARGET_CLASS, LinkageKeys.TARGET_SLOT],
                ]:
                    cur_class = linkages[class_key]
                    if cur_class == class_name:
                        # The class in the linkages matches class_name, so get all the referenced slots.
                        cur_slots = linkages[slot_key]
                        if isinstance(cur_slots, str):
                            cur_slots = [cur_slots]
                        for cur_slot in cur_slots:
                            if cur_slot not in slots:
                                slots += [cur_slot]
            elif isinstance(linkages, list):
                # The linkages is a list of dictionaries, so get the referenced slots
                # from each of the dictionaries.
                for cur_linkage in linkages:
                    slots += _get_slots_for_class(cur_linkage)
            else:
                raise ValueError(
                    f"Linkages must be a dict or list, but is of type {type(linkages)}: {linkages}"
                )
            return slots

        # Get the hardcoded lookup slots for the class
        lookup_slots = MAKE_ROW_INDEX_LOOKUPS.get(class_name, [])

        # Use all slots referenced in the class linkages as lookup slots
        if self.config.get(ConfigKeys.CLASS_LINKAGES, None):
            for target_linkages in self.config[ConfigKeys.CLASS_LINKAGES].values():
                for linkages in target_linkages.values():
                    lookup_slots += _get_slots_for_class(linkages)

        # Use all slots referenced in the named class linkages as lookup slots
        if self.config.get(ConfigKeys.NAMED_CLASS_LINKAGES, None):
            for named_linkage in self.config[ConfigKeys.NAMED_CLASS_LINKAGES].values():
                for target_linkages in named_linkage.values():
                    for linkages in target_linkages.values():
                        lookup_slots += _get_slots_for_class(linkages)

        # Remove duplicates (but retain order, since it makes it easier for debugging)
        lookup_slots = list(dict.fromkeys(lookup_slots))

        return lookup_slots

    def load_all(
        self,
        data_files: Dict[str, List[Union[str, Path]]],
        data_frames: Dict[str, List[pd.DataFrame]],
    ):
        """Load all data from disk and create a GeneratorData object for all the data.

        Args:
            data_files (Dict[str, List[Union[str, Path]]]): All input data files to load for adding IDs to (in addition to the DataFrames in
                data_frames). The keys are the class name and the values are lists of files belonging to that class. These can be CSV, TSV,
                TXT, YAML, or YML files.
            data_frames (Dict[str, List[pd.DataFrame]]): All input DataFrames that we want to generate IDs for. The keys are the class names
                and the values are lists of DataFrames belonging to the class.
        """
        self.data: Dict[str, GeneratorData] = {}
        generated_slots = self.get_all_generated_slots_from_id_code()
        star_lookup_slots = MAKE_ROW_INDEX_LOOKUPS.get("*", [])
        all_data = merge_dicts_of_lists([data_files, data_frames])

        progress = ProgressCounter(
            {PREPARING_BARID: len(all_data)}, multiple_bars=False
        )
        with progress:
            for class_name, cur_data in all_data.items():
                self.data[class_name] = GeneratorData(
                    class_name,
                    cur_data,
                    schema=self.schema,
                    generated_slots_for_selectors=generated_slots.get(class_name, []),
                    primary_key=self.primary_keys.get(class_name),
                    for_merging=self.for_merging,
                )
                progress.update(PREPARING_BARID, 1)

        # Prepare the config linkage paths (by cleaning them). This function
        # requires that all the self.data objects have been generated (see above)
        self.prepare_config_linkage_paths()

        # Initialize the lookup tables (for fast searching) of all the data.
        # We need to do this here (instead of above) because self.get_class_lookup_slots
        # requires that the linkage paths in the config file have been prepared and
        # cleaned by calling self.prepare_config_linkage_paths()
        for class_name, data in self.data.items():
            class_lookup_slots = self.get_class_lookup_slots(class_name)
            lookup_slots = list(set(class_lookup_slots + star_lookup_slots))
            data.init_lookup_table(lookup_slots)

    def create_bindings(self):
        """Create the function and data bindings. Should be called once all data has been loaded
        and finalized.
        """
        # Get all recognized classes
        class_linkages = self.config.get(ConfigKeys.CLASS_LINKAGES, {})
        all_classes = list(class_linkages.keys())
        all_classes += [
            class_name for lnk in class_linkages.values() for class_name in lnk.keys()
        ]
        all_classes += list(self.primary_keys.keys())
        all_classes = list(dict.fromkeys(all_classes))

        self.bindings = {
            "dat": DataBindings(
                self,
                root_class="",
                sub_class_names=all_classes,
                prefix="dat",
                replace_empty_values=False,
            ),
            # Same as dat, but if a value is empty then automatically convert it to id_data_bindings.EMPTY_VALUE
            "datEmpty": DataBindings(
                self,
                root_class="",
                sub_class_names=all_classes,
                prefix="datEmpty",
                replace_empty_values=True,
            ),
            "fn": FunctionBindings(self),
        }

    def prepare_config_linkage_paths(self):
        """Cleanup all linkage paths in the config file, acc

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

        # Clean up named_class_linkages
        if self.config.get(ConfigKeys.NAMED_CLASS_LINKAGES, None):
            for named_linkage in self.config[ConfigKeys.NAMED_CLASS_LINKAGES].values():
                for source_class, target_linkages in named_linkage.items():
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
        For example, the following will link the measures table to the sites table: Notice too that in the
        second dictionary in the list, we already know that the source_class is samples, since it is the
        target_class in the previous step, and so "source_class: samples" can be removed.

            - source_class: measures
              source_slot: sampleID
              target_class: samples
              target_slot: sampleID
            - source_class: samples
              source_slot: siteID
              target_class: sites
              target_slot: siteID

        We infer that the first item in the linkage path starts at source_class and the last item in the
        path ends at target_class. Along the path, the source class of the current path item is the target
        class of the previous path item.

        Args:
            source_class (str): The source class that we link from.
            target_class (str): The target class that we link to.
            linkages (Union[Dict, List[Dict]]): A single linkage path item or a list of linkage path items
                that we follow in order.
        """

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
            # values for the slots are stored. This applies only to generated slots (ie. that need to be generated
            # through ID code).
            if source_class in self.data:
                linkage[LinkageKeys.SOURCE_SLOT] = self.data[
                    source_class
                ].make_initial_slot_names_if_generated_slots(
                    linkage[LinkageKeys.SOURCE_SLOT]
                )
            if target_class in self.data:
                linkage[LinkageKeys.TARGET_SLOT] = self.data[
                    target_class
                ].make_initial_slot_names_if_generated_slots(
                    linkage[LinkageKeys.TARGET_SLOT]
                )

            prev_class = linkage[LinkageKeys.TARGET_CLASS]

    def rename_id_code_colums(self, id_code_df: pd.DataFrame):
        """Rename the code columns in the specified DataFrame, so that they follow the correct naming
        convention for code columns.

        Code columns start with the string IDCodeColumns.CODE_PREFIX ("code"), then a 0-based integer
        in the string format IDCodeColumns.CODE_SUFFIX (eg. "{:03d}), for example, code000, code001, etc.
        The number assigned to the column increases from left to right in the order that the columns appear.

        Args:
            id_code_df (pd.DataFrame): The DataFrame to rename the columns. This DataFrame is modified
                in place.
        """
        # Rename any column that starts with the word "code", so that they're in the form "code000" (maintaining the
        # original order)
        code_columns = [
            c for c in id_code_df.columns if c.startswith(IDCodeColumns.CODE_PREFIX)
        ]
        code_columns_map = {
            c: self.make_code_column_name(idx) for idx, c in enumerate(code_columns)
        }
        id_code_df.columns = [code_columns_map.get(c, c) for c in id_code_df.columns]

    def prepare_id_code(self, id_code_files: List[Dict]):
        """Load and prepare the ID generation code from the specified file. The file should contain all the
        columns found in IDCodeColumns.

        Args:
            id_code_files (List[Dict]): List of dictionaries specifying the files containing the ID code, or
                DataFrames containing the ID code. If DataFrames then they are treated as regular files that
                have already been loaded into memory. The
                dictionaries are in any of the following forms:
                    1) {"id_code_file": "file.xlsx", "id_code_sheet": "sheet"}. id_code_file
                       can be a CSV, TSV, or XLSX file. If an XLSX file then "id_code_sheet" specifies which
                       sheet in the Excel file to use. If "id_code_sheet" is None or missing then the first
                       sheet is used.
                    2) {"id_code_df: df}. df is a pd.DataFrame of the ID code. It is treated the same as a
                       code file that has already been loaded into memory.
        """
        self.id_code_df = pd.DataFrame()
        if not id_code_files:
            return

        # Load all code files and concatenate them into one DataFrame
        id_code_df = []
        for cur_id_code_file in id_code_files:
            if "id_code_df" in cur_id_code_file:
                cur_id_code_df = cur_id_code_file.get("id_code_df")
            else:
                id_code_file = cur_id_code_file.get("id_code_file")
                id_code_sheet = cur_id_code_file.get("id_code_sheet", None)
                if os.path.splitext(id_code_file)[1].lower() == ".xlsx":
                    cur_id_code_df = pd.read_excel(
                        id_code_file, id_code_sheet if id_code_sheet else 0
                    )
                else:
                    cur_id_code_df = read_data_frame(id_code_file)

            self.rename_id_code_colums(cur_id_code_df)
            id_code_df.append(cur_id_code_df)

        if len(id_code_df) == 0:
            return

        id_code_df = pd.concat(id_code_df)

        # Drop rows where either the class or slot are empty
        id_code_df = id_code_df.dropna(
            subset=[IDCodeColumns.CLASS, IDCodeColumns.SLOT], axis=0, how="any"
        )
        # Drop rows where all code columns are empty
        code_columns = [
            c for c in id_code_df.columns if c.startswith(IDCodeColumns.CODE_PREFIX)
        ]
        id_code_df = id_code_df.dropna(subset=code_columns, axis=0, how="all")
        # Drop duplicates where the class and slot are equal, keeping the last duplicate only
        id_code_df = id_code_df.drop_duplicates(
            subset=[IDCodeColumns.CLASS, IDCodeColumns.SLOT], keep="last"
        )

        self.id_code_df = id_code_df

    def get_code_selectors_from_row(self, class_name: str, row_index: int) -> List[str]:
        """Get the code selectors associated with the specified row in the specified class.

        Args:
            class_name (str): The class to get the row from.
            row_index (int): The row index in the class to get the code selectors for.

        Returns:
            List[str]: A list of the code selectors associated with the row. If there are no
                code selectors then the default None code selector is returned as [None].
        """
        return self.data[class_name].get_code_selectors_from_row(row_index)

    def get_all_generated_slots_from_id_code(self) -> Dict[str, Dict[str, List[str]]]:
        """Get a list of all slots (and their class) that have ID code, as well as the code
        selector for the ID code if there is one.

        Returns:
            Dict[str, Dict[str, List[str]]]: A dictionary where the key is the class name
                and the values are sub-dictionaries. In the sub-dictionaries the keys are
                the code selectors (include the key None for code without a selector) and
                the values are list of slots in the class that have ID code.
        """
        # Determine all the ID slots that need to be calculated (in all classes).
        generated_slots = {}
        for _, row in self.id_code_df.iterrows():
            class_name = row[IDCodeColumns.CLASS]
            orig_slot = row[IDCodeColumns.SLOT]
            slot, selectors = get_slot_and_selectors_from_slot(orig_slot)
            # Add the class to generated_slots dictionary
            if class_name not in generated_slots:
                generated_slots[class_name] = {}
            for selector in selectors:
                # Add the selector to generated_slots[class_name] dictionary
                if selector not in generated_slots[class_name]:
                    generated_slots[class_name][selector] = []
                # Add the slot to generated_slots[class_name][selector]
                if slot not in generated_slots[class_name][selector]:
                    generated_slots[class_name][selector].append(slot)
        return generated_slots

    def run_generator(
        self,
        keep_extra_columns: bool,
        keep_tracking_columns: bool,
        keep_debug_columns: bool,
        remove_duplicates: bool,
    ) -> Dict[str, List[pd.DataFrame]]:
        """Run the generator and retrieve the final DataFrames.

        Args:
            keep_extra_columns (bool): If True, then keep the extra columns in the final DataFrame. These
                are columns that start with the string extra_and_tracking_slots.EXTRA_SLOT_PREFIX and end with the
                string extra_and_tracking_slots.EXTRA_SLOT_SUFFIX. If False then they are removed.
            keep_tracking_columns (bool): If True, then keep the tracking columns in the final DataFrame.
                These are columns that specify from which row and file/table each of the output rows was populated
                from. Tracking columns start with the string extra_and_tracking_slots.TRACKING_SLOT_PREFIX and end
                with the string extra_and_tracking_slots.TRACKING_SLOT_SUFFIX. If False then these columns are
                dropped.
            keep_debug_columns (bool): If True then keep additional columns for debugging. These are
                temporary columns that are used for running, such as columns containing the old IDs
                before generation was run, the hash column, etc.
            remove_duplicates (bool): If True then remove duplicates based on the primary keys of each
                class. In production this is typically True. If False then duplicates are retained,
                but an extra __drop column is added where the value is True if that row would
                have been dropped if remove_duplicates was True.

        Returns:
            Dict[str, List[pd.DataFrame]]: Dictionary where the keys are the class names and the values are
                lists of DataFrames belonging to the class, where all IDs have been generated.
        """
        self.make_all_ids()
        data_frames = {}
        total_rows = 0
        total_rows_minus_dropped_rows = 0
        total_dropped_rows = 0
        progress = ProgressCounter({FINALIZE_BARID: len(self.data)})
        with progress:
            for _, data in self.data.items():
                # finalize_data converts to DataFrames and drops duplicates
                (
                    cur_data_frames,
                    cur_total_rows,
                    cur_total_rows_minus_dropped_rows,
                    cur_total_dropped_rows,
                ) = data.finalize_data(
                    keep_extra_columns=keep_extra_columns,
                    keep_tracking_columns=keep_tracking_columns,
                    keep_debug_columns=keep_debug_columns,
                    remove_duplicates=remove_duplicates,
                )
                total_rows += cur_total_rows
                total_rows_minus_dropped_rows += cur_total_rows_minus_dropped_rows
                total_dropped_rows += cur_total_dropped_rows
                data_frames = merge_dicts_of_lists([data_frames, cur_data_frames])
                progress.update(FINALIZE_BARID, 1)
            logger.debug(
                f"Total rows: {total_rows}, total rows minus dropped rows: {total_rows_minus_dropped_rows}, total dropped rows: {total_dropped_rows}"
            )
        self.data_frames = data_frames

        logger.info(f"Finished making all IDs in {datetime.now() - self.tic}")

        return self.data_frames

    def make_all_ids(
        self,
        class_names: Optional[Union[str, List[str]]] = None,
        row_indices: Optional[Union[int, List[int]]] = None,
        skip_slots: Optional[Union[str, List[str]]] = None,
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
            skip_slots (Optional[Union[str, List[str]]], optional): If specified, then skip generating IDs for
                these slots.

        Raises:
            ValueError: A slot was specified in the ID code config file that does not exist in the loaded data for
                the class.
        """
        orig_row_indices = row_indices

        if not skip_slots:
            skip_slots = []
        if not isinstance(skip_slots, (list, tuple)):
            skip_slots = [skip_slots]

        # We only output progress information if all classes and all row indices are being generated.
        # This is the top-level call to make_all_ids and should only occur once.
        output_progress = class_names is None and row_indices is None

        def _log(level: str, s: str):
            if output_progress:
                getattr(logger, level)(s)
            pass

        _log("info", "Generating IDs, this may take some time...")

        # Get the current class and current row index that we are generating for. We will restore these
        # values once we're done with this function call. This will allow make_all_ids to be called
        # recursively, each with their own current_class and current_row_index.
        orig_current_class = self.current_class
        orig_current_row_index = self.current_row_index

        # Get all the class names to make IDs for
        if class_names is None:
            class_names = list(self.data.keys())
        elif isinstance(class_names, str):
            class_names = [class_names]

        # Total number of ID cells to generate. This is to report progress.
        self.total_ids = np.sum(
            [
                len(self.data[c]) * len(self.data[c].get_all_generated_slots())
                for c in class_names
            ]
        )
        if output_progress:
            # Set up the ProgressCounter to show progress bars
            totals = [
                # len(self.data[c]) * len(self.data[c].get_all_generated_slots())
                self.data[c].number_of_ids_to_calculate
                for c in class_names
            ]
            bar_totals = {
                class_name: total
                for class_name, total in zip(class_names, totals)
                if total
            }
            self.progress = ProgressCounter(
                bar_totals,
                multiple_bars=self.multi_bar_progress,
                install_output_hooks=True,
                total_title=TOTAL_IDS_TITLE,
            )
            progress = self.progress
        else:
            # We're not outputing progress, so use an EmptyCounter that has no output
            progress = EmptyCounter()

        with progress:
            for idx, class_name in enumerate(class_names):
                if progress.has_bar(class_name):
                    progress.show_bar(class_name)
                class_tic = datetime.now()
                _log(
                    "debug",
                    f"Making IDs for class '{class_name}' ({idx + 1}/{len(class_names)})",
                )

                # All the slots in the class that are IDs that need to be generated
                # all_slots = self.data[class_name].generated_slots

                # Determine the rows to iterate over (based on row_indices parameter)
                row_indices = orig_row_indices
                if row_indices is None:
                    # Generate IDs for all rows
                    row_indices = range(0, len(self.data[class_name]))
                else:
                    # Only generate IDs for the rows in row_indices. Make sure it's an array.
                    if not isinstance(row_indices, Iterable):
                        row_indices = [row_indices]

                # Iterate over all rows to generate the IDs
                for idx in row_indices:
                    selectors = self.get_code_selectors_from_row(class_name, idx)

                    # Iterate over all slots to generate an ID for in the current row
                    for slot in self.data[
                        class_name
                    ].get_generated_slots_with_selectors(selectors):
                        if slot not in self.data[class_name].columns:
                            raise ValueError(
                                f"Found slot '{slot}' in class '{class_name}' in ID code file that does not exist in the source data."
                            )
                        if slot in skip_slots:
                            continue

                        # Get the current value for the ID in the data. If it is non-null then it has already been
                        # generated and we can continue to the next loop.
                        v = self.data[class_name].get_data_value(slot, idx)
                        if not self.is_id_empty(v) and (
                            not self.requires_primary_key_index_generation(
                                class_name, slot, v
                            )
                        ):
                            continue

                        # Calculate the ID
                        self.calculate_id(class_name, slot, idx)
                _log(
                    "debug",
                    f"Made all IDs for class '{class_name}': {datetime.now() - class_tic}",
                )
                # _log("debug", f"Progress: {self.progress.get_progress_report()}")

        # Restore current_class and current_row_index in case make_all_ids has been called recursively
        self.current_class = orig_current_class
        self.current_row_index = orig_current_row_index

        # _log("info", f"Finished making all IDs in {datetime.now() - self.tic}")

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

    def get_code(
        self, class_name: str, slot: str, idx: int, code_selector: str
    ) -> Optional[str]:
        """Get the ID code for generating the ID for the specified slot.

        Args:
            class_name (str): The class the slot belongs to.
            slot (str): The slot to get the code for.
            idx (int): The code index to use. There may be multiple code columns in the ID code config
                file. We should execute the code starting with the first index (index 0). If the code
                results in an empty value, we should advance to the next code index, and continue until
                a non-empty value is obtained, or we reach a code index where no code is available.
            code_selector (str): A selector that specifies different code to access associated with the
                slot. This allows the same slot to have different code depending on this selector.
                In the ID code configuration file, code with a different selector are specified by adding
                the selector after a colon after the slot name. For example, if selector is "pooled" and the
                slot is "sampleID", then we would access code in the config file for the slot "sampleID:pooled".
                If code for this modified slot does not exist, then we will step down to trying to select code
                for the slot "sampleID" without the selector. If code_selector is None then no selector
                is added to the slot (ie. we would access code for the slot "sampleID" instead of
                "sampleID:pooled").

        Returns:
            Optional[str]: The code (at index idx) that generates the ID for the slot. None if no code
                is available.
        """
        select_slots = []  # [slot]

        code_selector = None if pd.isna(code_selector) else str(code_selector)
        if code_selector is not None and code_selector != "":
            select_slots = [
                add_code_selector_to_slot(slot, code_selector)
            ] + select_slots
        else:
            select_slots = [slot]

        # Get the code column name at the index, and make sure the column exists.
        code_column = self.make_code_column_name(idx)
        if code_column not in self.id_code_df.columns:
            return None

        # Get all the code for the class. We will select the code for the slot from this.
        id_code_class_df = self.id_code_df[
            self.id_code_df[IDCodeColumns.CLASS] == class_name
        ]

        # Try to get the code for the slots in select_slots. Once we find a slot with code we will use it.
        code = None
        for cur_slot in select_slots:
            code = id_code_class_df[id_code_class_df[IDCodeColumns.SLOT] == cur_slot]
            if len(code) > 0:
                break
        if code is None or len(code) == 0:
            return None

        code = code[code_column].iloc[0]
        return code

    def update_progress(self, class_name: str, inc: int):
        """Update the progress of the specified class with the progress bars.

        Args:
            class_name (str): The class name to update the progress for.
            inc (int): The number to increment the progress by. Each single generated ID should result
                in a single increment.
        """
        self.progress.update(class_name, inc)

    def get_linked_rows(
        self,
        source_class: str,
        source_index: Union[int, List[int]],
        target_class: str,
        max_rows: Optional[int] = None,
        ignore_indices: Optional[List[int]] = None,
        linkage_path: Optional[Union[Dict, List[Dict]]] = None,
        return_indices: bool = False,
        ignore_current_row: bool = False,
    ) -> Union[np.ndarray, Tuple[np.ndarray, np.ndarray]]:
        """Get the rows in target_class, that are linked to the row(s) at index source_index in source_class. Use the linkage path to determine
        the linking steps required to go from source_class to target_class. If linkage_path is None then we use the
        linkage path found in the config file (under the ConfigKeys.CLASS_LINKAGES key). Typically, rows in different classes
        are linked by foreign keys and primary keys.

        Note that the returned rows may have IDs that have not yet been calculated.

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
            return_indices (bool): If True then return the indices of all the rows. The return value
                will be a tuple of the form (rows, indices) where indices is a 1-D array of indices for each row. If False
                then only the rows are returned. Defaults to False.
            ignore_current_row (bool): If True then do not include the current row in the results. If False then
                the current row might be included in the results.

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

        if source_class not in self.data or target_class not in self.data:
            return _ret_value(None, None)

        # If the source_class and target_class are the same, then we just return the source row
        # (in class source_class and row source_index). Only do this if linkage_path is None. If
        # linkage_path is not None then it's possible that the caller is requesting a row other
        # than the current row. If ignore_current_row is True (and source_class == target_class)
        # then we do not return the current row.
        if (
            source_class == target_class
            and linkage_path is None
            and not ignore_current_row
        ):
            rows = self.data[source_class].get_rows_at_index(source_index)
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
        rows = self.data[source_class].get_rows_at_index(source_index)
        indices = [source_index]
        if rows is None:
            raise ValueError(
                f"No row(s) at index {source_index} in class '{source_class}'"
            )
        orig_ignore_indices = ignore_indices.copy() if ignore_indices else []
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
            rows = rows[:, self.data[cur_class].get_column_index(linkage_source_slot)]
            # Get all values to match, obtained from the source table, that we want to match
            # in the target table.
            row_match = tuple(set(map(tuple, rows)))

            # If ignore_current_row is True and the target class is the current source class then add the
            # current row index (source_index) to ignore_indices. We will NOT return the current row in
            # the results.
            if ignore_current_row and source_class == linkage_target_class:
                ignore_indices = orig_ignore_indices.copy()
                if ignore_indices is None:
                    ignore_indices = []
                ignore_indices.append(source_index)
            else:
                ignore_indices = orig_ignore_indices

            # Get the rows
            rows, indices = self.data[linkage_target_class].get_rows_equal(
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
        ignore_current_row: bool = False,
    ) -> Union[np.ndarray, Tuple[np.ndarray, int]]:
        """Get the first row in target_class that is linked to the row at index source_index in the class source_class.

        Note that the returned row may have IDs that have not yet been calculated.

        Args:
            source_class (str): The source class.
            source_index (int): The row index in the source class that we want to get the linked rows for.
            target_class (str): The target class to get the linked rows from.
            linkage_path (Optional[Union[Dict, List[Dict]]], Optional): The configuration specifying how to link from source_class to target_class. If None
                then the default linkage path from source_class to target_class in the config file is used. Defaults to None.
            return_index (bool): If True then return the index of the first linked row, in addition to
                the row. The return value will be the tuple (row, index)
            ignore_current_row (bool): If True then do not include the current row in the results. If False then
                the current row might be included in the results.

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
            ignore_current_row=ignore_current_row,
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
        generate_index_if_primary_key: bool = True,
        ignore_current_row: bool = False,
    ) -> Any:
        """Get the first value in target_class and slot target_slot that is linked to the row in source_class at row index
        source_index, using the linkage_path to determine how to link from source_class to target_class. If linkage_path
        is None then we use the linkage path found in the config file (self.config[ConfigKeys.CLASS_LINKAGES]).

        If the value is for an ID that needs to be generated then it will be generated and the IDValue returned. If
        generate_index_if_primary_key is True and the value is for a primary key, then the returned IDValue will
        have its index calculated.

        Args:
            source_class (str): The source class we are linking from.
            source_index (int): The row index in the source class to link from.
            target_class (str): The target class that we want to get the linked value from.
            target_slot (str): The slot in the target class to get the value from.
            linkage_path (Optional[Union[Dict, List[Dict]]], Optional): Configuration of how to link from source_class to
                target_class. If None then the default linkage in the config file is used. Defaults to None.
            generate_index_if_primary_key (bool): If True and the target class and slot are for a primary key, then
                generate the index of the first linked value before returning it if the index has not yet been generated.
                In a lot of cases we do not need the index, and calculating the index can result in circular dependencies
                that cause an error.
            ignore_current_row (bool): If True then do not include the current row in the results. If False then
                the current row might be included in the results.

        Returns:
            Any: The first linked value in the target class and slot. If no linked value is found then None is returned.
        """
        row, idx = self.get_first_linked_row(
            source_class,
            source_index,
            target_class,
            linkage_path,
            return_index=True,
            ignore_current_row=ignore_current_row,
        )
        if row is None:
            return None

        # If the target slot is an ID that needs to be generated, then generate it and return the value
        if target_slot in self.data[target_class].get_all_generated_slots():
            cur_value = self.data[target_class].get_value_from_row(row, target_slot)
            # The value needs to be generated if it is empty (ie. None, EMPTY_OBJ, or root_id is None) or
            # if the root ID has been generated but its index has not (ie. generate_primary_key_index() hasn't been called yet)
            if self.is_id_empty(cur_value) or (
                generate_index_if_primary_key
                and self.requires_primary_key_index_generation(
                    target_class, target_slot, cur_value
                )
            ):
                return self.calculate_id(
                    target_class,
                    target_slot,
                    idx,
                    generate_index_if_primary_key=generate_index_if_primary_key,
                )

        # return row[self.get_column_index(target_class, target_slot)]
        return self.data[target_class].get_value_from_row(row, target_slot)

    def requires_primary_key_index_generation(
        self, class_name: str, slot: str, id_value: Any
    ) -> bool:
        """Test if the value (possibly an IDValue) needs to have its index generated, due to it being
        a primary key that has not yet been grouped/indexed.

        If id_value is not an IDValue (eg. it might be a string or float), then False is always returned.

        Args:
            class_name (str): The class the id_value belongs to.
            slot (str): The slot in the class that the id_value belongs to.
            id_value (Any): The value to test.

        Returns:
            bool: True if the value's index needs to be generated by calling generate_primary_key_index(), False
                otherwise.
        """
        if not isinstance(id_value, IDValue):
            return False
        return (
            self.data[class_name].primary_key == slot
            and not id_value.is_index_generated()
        )

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
                dictionaries in the returned list.

                If the config file does not specify a linkage from source_class to target_class, then the default
                linking slot becomes TrackingSlots.SOURCE_FILE_AND_ROW.
        """
        if (
            not self.config.get(ConfigKeys.CLASS_LINKAGES, None)
            or source_class not in self.config[ConfigKeys.CLASS_LINKAGES]
            or target_class not in self.config[ConfigKeys.CLASS_LINKAGES][source_class]
        ):
            # If no class_linkages are specified in the config file, then link by the source file and row
            # tracking column.
            return {
                LinkageKeys.SOURCE_SLOT: TrackingSlots.SOURCE_FILE_AND_ROW,
                LinkageKeys.SOURCE_CLASS: source_class,
                LinkageKeys.TARGET_SLOT: TrackingSlots.SOURCE_FILE_AND_ROW,
                LinkageKeys.TARGET_CLASS: target_class,
            }

        # if source_class not in self.config[ConfigKeys.CLASS_LINKAGES]:
        #     return None
        linkage = self.config[ConfigKeys.CLASS_LINKAGES][source_class]
        return linkage.get(target_class, None)

    def is_id_empty(self, v: IDValue) -> bool:
        if isinstance(v, IDValue):
            return v.is_empty()
        return v is None or v is EMPTY_OBJ

    def calculate_id(
        self,
        class_name: str,
        slot: str,
        row_index: int,
        generate_index_if_primary_key: bool = True,
    ) -> Any:
        """Calculate the ID for the slot in the class at the specified row index. The ID is
        calculated based on the ID generation code for the class/slot combination, and is found
        in the ID code config file.

        Args:
            class_name (str): The class that the slot belongs to.
            slot (str): The slot to calculate the ID for.
            row_index (int): The row index in the class's DataFrame that we calculate the slot for.
            generate_index_if_primary_key (bool, optional): If True, and the slot is the primary key for
                the class, then also generate the index for the resulting IDValue. For IDValues that
                are not for a primary key we do not need the index. If the caller is creating a
                composite ID (ie. using several IDs to create one bigger ID) then it should typically
                not use the index (using the index for each component ID would lead to too many
                circular references where the index cannot be calculated due to its dependency
                on other IDs with indices).

        Returns:
            Any: The calculated ID.
        """

        def _is_id_ready(v: Any) -> bool:
            """Check if the IDValue is ready to return. The value is ready when it is of type IDValue
            and either we do not need the IDValue's index or the IDValue's index has been generated.
            The index gets generated by calling generate_primary_key_index(). We call this function
            multiple times, since there are many steps where a call to another function might result
            in the IDValue having its index generated.

            Args:
                v (Any): The IDValue to test.

            Returns:
                bool: True if the IDValue is ready to return, False otherwise.
            """
            return isinstance(v, IDValue) and (
                not generate_index_if_primary_key
                or not self.requires_primary_key_index_generation(class_name, slot, v)
            )

        if class_name not in self.data:
            return None

        orig_v = self.data[class_name].get_data_value(slot, row_index)
        if _is_id_ready(orig_v):
            return orig_v

        # Generate previous primary keys (in previous rows) if required. We do this so that when
        # we calculate the indices for the primary keys, the primary keys in earlier rows receive
        # the smaller index. In order for this to happen, the earlier primary keys must be calculated
        # first.
        if self.data[class_name].primary_key == slot and row_index > 0:
            # Keep on going up a row until we reach past the top or we reach a row
            # where the primary key has already started calculation
            prev_index = row_index - 1
            while prev_index >= 0:
                prev_v = self.data[class_name].get_data_value(slot, prev_index)
                if self.is_id_empty(prev_v):
                    self.calculate_id(class_name, slot, prev_index)
                else:
                    break
                prev_index -= 1

        # Generate the IDValue if it is currently empty
        if self.is_id_empty(orig_v):  # not isinstance(orig_v, IDValue):
            # We loop through all code columns for the slot. Once executing the code generates a
            # non-empty value (either returned from the code or with the "target" variable being set
            # in the code), we use that value as the generated ID and stop looping over the code
            # columns. If we have executed all the code columns and all of them have generated an
            # empty value, we return without setting the ID
            v = None
            interpreter = self.interpreter
            orig_symtable = interpreter.symtable

            code_selectors = self.data[class_name].get_code_selectors_from_row(
                row_index
            )

            has_value = False
            for code_selector in code_selectors:
                if has_value:
                    break
                code_idx = -1
                while not has_value:
                    code_idx += 1
                    code = self.get_code(class_name, slot, code_idx, code_selector)

                    if pd.isna(code) or not code:
                        if code_idx > 0:
                            v = None
                            has_value = True
                        break

                    orig_current_class = self.current_class
                    orig_current_row_index = self.current_row_index
                    self.current_class = class_name
                    self.current_row_index = row_index

                    interpreter.symtable = self.interpreter_clean_symtable.copy()
                    try:
                        v = interpreter(code, raise_errors=True)
                    except Exception as e:
                        # format_exc() will provide extra traceback information related to the exception that occurred
                        # when executing the code string.
                        logger.error("*" * 100)
                        logger.error(traceback.format_exc())
                        logger.error("=" * 100)
                        raise ValueError(
                            f"Error when calculating ID for '{class_name}.{slot}:{row_index}': {e}\nCode: {code}"
                        )
                    finally:
                        self.current_class = orig_current_class
                        self.current_row_index = orig_current_row_index

                    # If the variable "target" has been set by the code, then use that value instead
                    if "target" in interpreter.symtable:
                        v = interpreter.symtable["target"]

                    # If the code resulted in an empty value, continue to the next code column
                    if isna(v) or v == "":
                        continue

                    has_value = True
                    break

            interpreter.symtable = orig_symtable

            if isna(v):
                v = ""

            # IDs must be strings. Numbers like "1.0" will be loaded as an integer by Excel and possibly
            # other tools, so is indistinguishable from "1". To avoid this, get rid of the ".0" if it exists
            try:
                # It's alright for numbers that have a "_" in it (which is allowed in Python)
                if isinstance(v, str) and "." in v and "_" not in v:
                    f = float(v)
                    if f == int(f):
                        v = f"{int(f)}"
            except Exception:
                pass

            # During calculation of the value above, it's possible that we recursed into calculating
            # other IDs, which eventually led to calculating of the current ID (for class_name, slot, and
            # row_index). If that occurs, then we can stop here.
            new_v = self.data[class_name].get_data_value(slot, row_index)
            if _is_id_ready(new_v):
                return new_v

            v = self.data[class_name].set_data_value(slot, row_index, v)
        else:
            v = orig_v

        # If the slot is the primary key, then calculate the remainder of the row, so we can determine if the
        # row is a duplicate or not of all other rows generated so far that have the same primary key value.
        # If it is a duplicate, we reuse an existing primary key ID from the duplicates. If it is not
        # a duplicate we make sure the primary key value is unique.
        if generate_index_if_primary_key and self.requires_primary_key_index_generation(
            class_name, slot, v
        ):
            v.index_in_progress = True
            self.make_all_ids(class_name, row_index, skip_slots=[slot])

            # While generating other IDs with self.make_all_ids above, it's possible that we generated the
            # primary key index. We check that here.
            new_v = self.data[class_name].get_data_value(slot, row_index)
            if _is_id_ready(new_v):
                return new_v

            # Grouping the primary keys will either group the new calculated ID with an existing
            # ID where the rows are identical, or will add an index to the end of the new ID
            # if there are no identical rows but the new ID is already in use (ie. we will
            # make the new ID unique)
            v = self.data[class_name].generate_primary_key_index(row_index)

        # Update progress for each ID that gets generated. Note that for primary keys the
        # index must be generated for the ID generation to be complete
        if self.data[class_name].primary_key != slot or (
            self.data[class_name].primary_key == slot and v.is_index_generated()
        ):
            self.update_progress(class_name, 1)

        if not _is_id_ready(v):
            raise RuntimeError(
                f"ID is not ready for returning when calculating ID for {class_name}.{slot}:{row_index}."
            )

        return v

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
        data = self.data[class_name]
        return (
            data.get_data_value(TrackingSlots.SOURCE_CLASS, row_index),
            data.get_data_value(TrackingSlots.SOURCE_ROW, row_index),
        )

    def get_current_source_class_and_row(self) -> Tuple[Optional[str], Optional[int]]:
        """Get the source class and source row that was used to populate the current class and current row.

        Returns:
            Tuple[Optional[str], Optional[int]]: A tuple of the form ("source_class", source_row), or (None, None)
                if the source class and row could not be retrieved.
        """
        return self.get_source_class_and_row(self.current_class, self.current_row_index)

    def get_source_file_and_row(
        self, class_name: str, row_index: int
    ) -> Tuple[Optional[str], Optional[int]]:
        """Get the source file and source row that were used to populate the row at row_index (0-based) of
        the table class_name.

        Args:
            class_name (str): The class name.
            row_index (int): The row index (0-based) in the table for class_name that we want the source class
                and source row of.

        Returns:
            Tuple[Optional[str], Optional[int]]: A tuple of the form ("source_file", source_row), or (None, None)
                if the source file and row could not be retrieved.
        """
        data = self.data[class_name]
        source_file = data.get_data_value(TrackingSlots.SOURCE_FILE, row_index)
        source_row = data.get_data_value(TrackingSlots.SOURCE_ROW, row_index)
        if isinstance(source_row, str) and "_" not in source_row:
            source_row = int(source_row)
        return (
            source_file,
            source_row,
        )

    def get_current_source_file_and_row(self) -> Tuple[Optional[str], Optional[int]]:
        """Get the source file and source row that was used to populate the current class and current row.

        Returns:
            Tuple[Optional[str], Optional[int]]: A tuple of the form ("source_file", source_row), or (None, None)
                if the source file and row could not be retrieved.
        """
        return self.get_source_file_and_row(self.current_class, self.current_row_index)

    def get_class_short_name(self, class_name: str) -> Optional[str]:
        """Get the short name of the specified class name, according to the configuration file.

        Args:
            class_name (str): The class name to get the short name of (eg. "sampels" -> "sm")

        Returns:
            Optional[str]: The short name of the class, or None if no short name is defined.
        """
        return self.config.get(ConfigKeys.TABLES_TO_SHORTNAMES, {}).get(
            class_name, None
        )

    def save_all(
        self,
        output_dir: str,
    ) -> Tuple[Dict[str, List[Path]], Dict[str, List[pd.DataFrame]]]:
        tic = datetime.now()
        logger.info(f"Saving all data to {output_dir}")
        output_data_files = {}
        output_data_frames = {}
        for data in self.data.values():
            cur_output_data_files, cur_output_data_frames = data.save_data(output_dir)
            output_data_files = merge_dicts_of_lists(
                [output_data_files, cur_output_data_files]
            )
            output_data_frames = merge_dicts_of_lists(
                [output_data_frames, cur_output_data_frames]
            )

        logger.info(f"Finished saving: {datetime.now() - tic}")
        return output_data_files, output_data_frames
