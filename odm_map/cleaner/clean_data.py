"""
Class for cleaning data.

The cleaning options are specified with the clean_operations parameters of the functions clean_data and clean_single_data. It is
dictionary where the keys are the cleaning option names and the values are the parameters for the option. The type of the
parameters depend on the option. See the clean_data function for a list of options and their parameters.
"""

from pathlib import Path
import pandas as pd
import os
import re
from typing import Tuple, List, Union, Optional, Dict, Any, Callable
import yaml

from linkml_runtime import SchemaView
from linkml_runtime.linkml_model.meta import EnumDefinition

from odm_map.utils.general_utils import (
    read_data_frame,
    save_data_frame,
    get_unique_output_file,
    make_multivalued,
    EXCEL_FILE_KEY,
)
from odm_map.utils.logger import get_logger, make_logger_bullet_list
from odm_map.utils.extra_and_tracking_slots import is_extra_or_tracking_slot
from odm_map.utils.schema_utils import (
    get_ranges_of_slot,
    all_classes_without_tree_root,
    validate_columns_with_schema,
)
from odm_map.progress import ProgressCounter

CLEAN_BARID = "Cleaning Data"

logger = get_logger(__name__)


class DataCleaner(object):
    def __init__(
        self,
        schema: Optional[Union[str, Path, SchemaView]] = None,
    ):
        self.log = {}
        self.immediate_output_log = False
        if isinstance(schema, (str, Path)):
            self.schema = SchemaView(schema)
        else:
            self.schema = schema

    def add_to_log(self, level: str, msg: str):
        if level not in self.log:
            self.log[level] = []
        self.log[level].append(msg)
        if self.immediate_output_log:
            self.output_all_log(clear=True)

    def output_all_log(self, clear: bool):
        for level, log in self.log.items():
            for msg in log:
                getattr(logger, level)(msg)
        if clear:
            self.log = {}

    def clean_remove_unknown_columns(
        self, df: pd.DataFrame, class_name: str
    ) -> pd.DataFrame:
        """Cleaning operation to remove unknown columns from the DataFrame.

        Args:
            df (pd.DataFrame): The DataFrame to remove the unknown columns from. A copy of this
                DataFrame is made with the original left unchanged.
            class_name (str): The class name that the DataFrame belongs to. We use this class
                to find the known columns.

        Returns:
            pd.DataFrame: The DataFrame with unknown columns removed.
        """
        if class_name not in all_classes_without_tree_root(self.schema):
            logger.debug(
                f"Not removing unknown columns for class {class_name} since class is not recognized"
            )
            return df

        logger.debug(f"Removing unknown columns for class {class_name}")

        class_definition = self.schema.induced_class(class_name)

        keep_columns = [
            c
            for c in df.columns
            if is_extra_or_tracking_slot(c) or c in class_definition.attributes
        ]
        unknown_columns = [c for c in list(df.columns) if c not in keep_columns]
        if len(unknown_columns) > 0:
            for c in unknown_columns:
                logger.warning(f"Removed unrecognized column: {c}")

        return df[keep_columns].copy()

    def clean_format_columns(
        self,
        df: pd.DataFrame,
        class_name: str,
        format_columns_options: Union[str, List[str]],
    ) -> pd.DataFrame:
        """Cleaning operation to format all column names. See DataCleaner.clean_data for all available cleaning options (specified
        with the "format_columns" clean_option).

        Args:
            df (pd.DataFrame): The DataFrame to clean the column names of. A copy of this DataFrame is made and
                the original is left unchanged.
            class_name (str): The class name that the DataFrame belongs to. It must exist in the schema for the DataCleaner.
            format_columns_options (Union[str, List[str]]): The formatting operations top apply to the column names.
                See clean_data for a list of all available formatting options (specified with the "format_columns" clean_option).

        Returns:
            pd.DataFrame: The DataFrame with the column names formatted.
        """
        if class_name not in all_classes_without_tree_root(self.schema):
            logger.debug(
                f"Not removing unknown columns for class {class_name} since class is not recognized"
            )
            return df

        logger.debug(f"Removing unknown columns for class {class_name}")

        if isinstance(format_columns_options, str):
            format_columns_options = [format_columns_options]

        columns = []
        for val in df.columns:
            if is_extra_or_tracking_slot(val):
                columns.append(val)
                continue
            for options in format_columns_options:
                if isinstance(options, str):
                    options = yaml.safe_load(options)
                    if isinstance(options, str):
                        options = {options: True}
                for option, param in options.items():
                    if option == "lowercase":
                        val = val.lower()
                    if option == "uppercase":
                        val = val.upper()
                    if option == "alpha_numeric_underscore":
                        val = re.sub("[^A-Za-z0-9]", "_", val)
                    if option == "single_underscores":
                        val = re.sub("__+", "_", val)
                    if option == "trim_trailing_underscores":
                        val = val.rstrip("_")
                    if option == "trim_whitespace":
                        val = re.sub(r"^\s*", "", val)
                        val = re.sub(r"\s*$", "", val)
                    if option == "remove_chars":
                        for ch in param:
                            val = val.replace(ch, "")
                    if option == "remove_special":
                        val = re.sub(r"[^A-Za-z0-9\s]", "", val)
            columns.append(val)

        changes = [
            f"{orig_column} -> {new_column}"
            for orig_column, new_column in zip(df.columns, columns)
            if orig_column != new_column
        ]
        if len(changes) > 0:
            changes = sorted(changes, key=lambda x: str(x).lower())
            changes_str = make_logger_bullet_list(changes)
            logger.info(f"The following column name changes were made:\n{changes_str}")

        df = df.copy()
        df.columns = columns

        columns_without_tracking_slots = [
            c for c in df.columns if not is_extra_or_tracking_slot(c)
        ]
        validate_columns_with_schema(
            columns_without_tracking_slots,
            self.schema,
            class_name,
            file=None,
            show_log=True,
        )

        return df

    def add_to_change_history(
        self,
        change_history: Dict,
        class_name: str,
        slot_name: str,
        old_value: str,
        new_value: str,
    ):
        if class_name not in change_history:
            change_history[class_name] = {}
        if slot_name not in change_history[class_name]:
            change_history[class_name][slot_name] = {}
        if old_value not in change_history[class_name][slot_name]:
            change_history[class_name][slot_name][old_value] = {}
        if new_value not in change_history[class_name][slot_name][old_value]:
            change_history[class_name][slot_name][old_value][new_value] = 0
        change_history[class_name][slot_name][old_value][new_value] += 1

    def report_change_history(self, change_history: Dict, clean_title: str):
        # Report changes history
        for class_name, class_data in change_history.items():
            for slot_name, slot_data in class_data.items():
                changes_items = []
                for old_val, old_val_data in slot_data.items():
                    for new_val, num_changes in old_val_data.items():
                        if new_val is not None:
                            cur_changes = f"{old_val} -> {new_val} ({num_changes} time{'' if num_changes == 1 else 's'})"
                        else:
                            cur_changes = f"{old_val if old_val else '<empty>'} ({num_changes} time{'' if num_changes == 1 else 's'})"
                        changes_items.append(cur_changes)
                changes_items = sorted(changes_items, key=lambda x: str(x).lower())
                changes_str = make_logger_bullet_list(changes_items)
                changes_str = f"{clean_title}: class '{class_name}', slot '{slot_name}':\n{changes_str}"
                self.add_to_log("warning", changes_str)

    def general_map_slot(
        self,
        clean_title: str,
        change_history: Dict,
        unknown_enums_history: Dict,
        df_column: pd.Series,
        class_name: str,
        slot_name: str,
        source_values: List[str],
        target_values: List[str],
        can_be_anything: bool,
        source_value_formatter: Callable[[str], str] = None,
    ) -> pd.Series:
        """A general cleaning function for cleaning a single slot in a class. This is called by self.general_map_class.

        It works by performing a simple mapping from source_values[idx] to target_values[idx]. In general, given a value
        v in the slot, the value gets mapped to target_values[source_values.index(source_valu_formatter(v))].

        A history of mapped values is retained in change_history, and a history of values that are not valid enum
        values is retained in unknown_enums_history. Both of these are used to report which changes/errors have
        been made to the user.

        Args:
            clean_title (str): A descriptive title of the cleaning operation, such as "Added ontology IDs". This is used to
                report the results to the user.
            change_history (Dict): Receives a history of which changes/mappings were made. The integer value at
                change_history[class_name][slot_name][old_value][new_value] is the number of times we mapped from
                old_value to new_value for the given class and slot.
            unknown_enums_history (Dict): Receives a history of which enum values that were encountered that are not
                allowable enum values. This will only be populated if the parameter can_be_anything is False.
                Typically, can_be_anything will be set to True if the slot has at least one range that is not
                an enumeration (eg. a string or number). If the slot has ranges that are only enumerations
                then can_be_anything should be False and unknown_enums_history will receive the unknown enum
                values. This dictionary has a count of the number of unknown values at
                unknown_enums_history[class_name][slot_name][value][None]
            df_column (pd.Series): The column that we are cleaning. This is the column taken from the class named
                class_name and the slot named slot_name. A copy will be made and modified, with the original left
                unchanged.
            class_name (str): The name of the class that df_column belongs to.
            slot_name (str): The slot (in class class_name) that df_column represents.
            source_values (List[str]): The mapping source values. The mapping performed is target_values[source_values.index(v)]
            target_values (List[str]): The mapping target values. The mapping performed is target_values[source_values.index(v)]
            can_be_anything (bool): If True, then the values in the slot can take on any value, so
                unknown_enums_history will remain unchanged. It is usually set to True if the slot has at
                least one range that is not an enumeration. If False then if a value in the slot is not
                found in source_values, then it is counted as an invalid value and stored in unknown_enums_history.
            source_value_formatter (Callable[[str], str], optional): _description_. Defaults to None.

        Returns:
            pd.Series: A copy of the column df_column with all the cleaning/mapping performed according to
                the parameters.
        """
        if class_name not in all_classes_without_tree_root(self.schema):
            logger.debug(
                f"Skipping '{clean_title}' for class {class_name} since class is not recognized"
            )
            return df_column

        logger.debug(f"{clean_title} for class {class_name}")

        df_column = df_column.copy()
        slot_defn = self.schema.induced_slot(slot_name, class_name)

        if source_value_formatter is None:

            def _mirror_value(v):
                return v

            source_value_formatter = _mirror_value

        def _get_mapped_value(v) -> str:
            if slot_defn.multivalued:
                v = make_multivalued(v)
            else:
                v = [v]
            for v_idx in range(len(v)):
                old_v = v[v_idx]
                try:
                    source_v = source_value_formatter(old_v)
                    idx = source_values.index(source_v)
                    new_v = target_values[idx]
                    v[v_idx] = new_v
                    if new_v != old_v:
                        # Add the class name, slot name, original value, new value to the changes history
                        # We report this to the user
                        self.add_to_change_history(
                            change_history, class_name, slot_name, old_v, new_v
                        )
                except Exception:
                    if not can_be_anything:
                        # Add the class name, slot name, original value to the history of unknown enum
                        # values. We report this to the user
                        self.add_to_change_history(
                            unknown_enums_history, class_name, slot_name, old_v, None
                        )
                    pass
            if slot_defn.multivalued:
                return v
            return v[0]

        # Perform the cleaning, by mapping from source_values[idx] to target_values[idx]
        df_column = df_column.map(_get_mapped_value)

        return df_column

    def general_map_class(
        self,
        clean_title: str,
        df: pd.DataFrame,
        class_name: str,
        report_unknown_values_only: bool,
        get_source_values: Callable[[EnumDefinition], str],
        get_target_values: Callable[[EnumDefinition], str],
        source_value_formatter: Callable[[str], str],
    ) -> pd.DataFrame:
        """A general cleaning operation to be called for each class that we want to clean. It works by formatting all values
        (using the function source_value_formatter) in the class's DataFrame for all slots that are enumerations, then mapping
        these values to new values. The lists returned by get_source_values and get_target_values will define which
        formatted source values get mapped to which target values. For example, if a formatted value matches
        get_source_values(enum)[idx], then it gets mapped to get_target_values(enum)[idx].

        Note that this function works by calling self.general_map_slot(...) on all enum slots in the class.

        Args:
            clean_title (str): A descriptive title of the cleaning operation, such as "Added ontology IDs". This is used to
                report the results to the user.
            df (pd.DataFrame): The DataFrame for the class. A copy is made and modified (and returned), with the original
                value left unchanged.
            class_name (str): The name of the class that the DataFrame belongs to.
            report_unknown_values_only (bool): If True, then the clean operation will only report unknown enumeration
                values found in each enum slot of the DataFrame. In this case, get_source_values, get_target_values,
                and source_value_formatter should all be None
            get_source_values (Callable[[EnumDefinition], str]): Function that takes an EnumDefinition as a parameter and
                returns a list of source values for mapping for the enum. For a given enum, get_source_values(enum)[idx]
                maps to get_target_values(enum)[idx]. If get_source_values is None, then the default will be to return
                all permissible values of the enum (ie. list(enum.permissible_values.keys()))
            get_target_values (Callable[[EnumDefinition], str]): Function that takes an EnumDefinition as a parameter and
                returns a list of target values for mapping for the enum. For a given enum, get_source_values(enum)[idx]
                maps to get_target_values(enum)[idx]. If get_target_values is None, then the default will be to return
                all permissible values of the enum (ie. list(enum.permissible_values.keys()))
            source_value_formatter (Callable[[str], str]): Function that formats all the source values within the slots
                of the DataFrame before trying to map (from get_source_values(enum)[idx] to get_target_values(enum)[idx]).
                If None then the default behavior is to use the source values unchanged when mapping.

        Returns:
            pd.DataFrame: A copy of df with all the slots that are enumerations cleaned according to the parameters.
        """
        if report_unknown_values_only and (
            get_source_values is not None
            or get_target_values is not None
            or source_value_formatter is not None
        ):

            def _is_none(v):
                return "None" if v is None else "Not None"

            raise ValueError(
                f"report_unknown_values_only is True but the following values must all be None: get_source_values ({_is_none(get_source_values)}), get_target_values ({_is_none(get_target_values)}), source_value_formatter ({_is_none(source_value_formatter)})"
            )

        logger.debug(f"{clean_title}: class '{class_name}'")
        df = df.copy()

        def _get_enum_permissible_values(enum: EnumDefinition) -> List[Optional[str]]:
            # By default, the get_source_values and get_target_values functions simply returns the EnumDefinition's permissible values
            # unchanged
            return list(enum.permissible_values.keys())

        if get_source_values is None:
            get_source_values = _get_enum_permissible_values
        if get_target_values is None:
            get_target_values = _get_enum_permissible_values

        class_defn = self.schema.induced_class(class_name)

        change_history = {}
        unknown_enums_history = {}

        # Go through all the columns in the DataFrame and apply the mapping from
        # get_source_values(enum)[idx] to get_target_values(enum)[idx]
        for slot_name in df.columns:
            if slot_name not in class_defn.attributes:
                continue

            slot_ranges = get_ranges_of_slot(class_name, slot_name, self.schema)
            source_values = []
            target_values = []
            can_be_anything = False
            if slot_ranges:
                # For all of the ranges for the slot, get the enum types. Based on the enum values,
                # determine which source values get mapped to which target values.
                for slot_range in slot_ranges:
                    # Get enumeration for the slot range, if there is one.
                    enum = self.schema.all_enums().get(str(slot_range), None)
                    if enum is not None:
                        # Get the source and target values. We map from cur_source_values[idx] to cur_target_values[idx]
                        cur_source_values = get_source_values(enum)
                        cur_target_values = get_target_values(enum)

                        # Save the current source and target values, retaining their order
                        # We will map from source_values[idx] to target_values[idx]
                        source_values.extend(cur_source_values)
                        target_values.extend(cur_target_values)
                    else:
                        can_be_anything = True

            if source_values and target_values:
                # There are source and target values, so perform the mapping of each row
                # for slot_name from source_values[idx] to target_values[idx] when possible
                df[slot_name] = self.general_map_slot(
                    clean_title,
                    change_history,
                    unknown_enums_history,
                    df[slot_name],
                    class_name,
                    slot_name,
                    source_values,
                    target_values,
                    can_be_anything,
                    source_value_formatter,
                )

        self.report_change_history(
            unknown_enums_history if report_unknown_values_only else change_history,
            clean_title,
        )

        return df

    def clean_single_data(
        self,
        data_file: Optional[Union[str, Path, Dict]],
        data_frame: Optional[pd.DataFrame],
        output_file: Optional[Union[str, Path]],
        class_name: str,
        clean_operations: List[Dict[str, Any]],
        max_rows: Optional[int] = 0,
    ) -> Tuple[str, pd.DataFrame]:
        """Clean either a single data file or a single DataFrame.

        Args:
            data_file (Optional[Union[str, Path, Dict]]): The file to clean. If a dictionary, then it is for an
                Excel file in the format {EXCEL_FILE_KEY: "file.xlsx", EXCEL_SHEET_KEY: "sheet_name"}. If specified then
                data_frame must be None.
            data_frame (Optional[pd.DataFrame]): The DataFrame to clean. If specified then data_file must be None.
            output_file (Optional[Union[str, Path]]): The file to save the cleaned data to. This should
                be different than the input_file to avoid overwriting the original. If None then the cleaned
                data is not saved to disk, but the cleaned DataFrame is still returned.
            class_name (str): The class name that the data_file or data_frame is for. This should be a class name found in
                the schema.
            clean_operations (List[Dict[str, Any]]): List of dictionaries specifying all the cleaning operations to perform.
                The key of each dictionary specifies which operation to perform and the value is the parameters for that
                operation. The operations are performed in the same order as they appear in the list. See clean_data for all
                available operations
            max_rows (Optional[int]): Maximum number of rows to clean from the file or DataFrame. The returned DataFrame
                and save data will have at most this many rows. If 0 or None then clean all rows. Defaults to 0.

        Returns:
            Tuple[str, pd.DataFrame]: A tuple of (new file name, data frame). The DataFrame
                is the contents of the file with any required processing performed (eg.
                putting dates and datetimes into the correct string format)
        """
        if (
            output_file is not None
            and data_file is not None
            and output_file == data_file
        ):
            raise ValueError(
                f"The input file and output file must be different: {data_file=}, {output_file=}"
            )

        if output_file is not None and os.path.dirname(output_file):
            os.makedirs(os.path.dirname(output_file), exist_ok=True)

        if data_file is not None:
            logger.debug(f"Cleaning data from {data_file}")

            # Read the DataFrame from disk
            df = read_data_frame(
                data_file,
                nrows=max_rows if max_rows else None,
                keep_default_na=False,
                na_values=None,  # [""],
            )
        else:
            df = data_frame

        def _lowercase_minimize_spacing(v: str) -> str:
            # Make a value lowercase and remove consecutive spaces. This can be used for the
            # source_value_formatter parameter of self.general_map_class
            return re.sub("  +", " ", v.lower())

        # Clean the data
        for cur_operation in clean_operations:
            if len(cur_operation) == 0:
                continue
            elif len(cur_operation) > 1:
                raise ValueError(
                    f"A cleaning operation can only contain a single dictionary key, but more were found: {cur_operation}"
                )
            for clean_name, clean_params in cur_operation.items():
                if clean_name == "correct_enums" and clean_params:

                    def _get_source_values(enum: EnumDefinition) -> List[Any]:
                        return [
                            re.sub("  +", " ", v.lower())
                            for v in list(enum.permissible_values.keys())
                        ]

                    df = self.general_map_class(
                        "Corrected capitalization and spacing",
                        df,
                        class_name,
                        False,
                        _get_source_values,
                        None,
                        _lowercase_minimize_spacing,
                    )
                elif clean_name == "add_ontology_ids_to_enums" and clean_params:

                    def _get_source_values(enum: EnumDefinition) -> List[Any]:
                        # Remove the ontology ID from the permissible values
                        vals = [
                            re.sub(clean_params["match_ontology_id"], "", v.strip())
                            for v in list(enum.permissible_values.keys())
                        ]
                        # Remove consecutive spaces, strip spaces from start/end, and make lowercase
                        vals = [re.sub("  +", " ", v).strip().lower() for v in vals]
                        return vals

                    if not isinstance(clean_params, Dict) or not isinstance(
                        clean_params.get("match_ontology_id", None), str
                    ):
                        raise ValueError(
                            "Parameter 'match_ontology_id' for action 'add_ontology_ids_to_enums' in config file must exist and be a string."
                        )

                    df = self.general_map_class(
                        "Added ontology IDs",
                        df,
                        class_name,
                        False,
                        _get_source_values,
                        None,
                        _lowercase_minimize_spacing,
                    )
                elif clean_name == "report_unknown_enum_values" and clean_params:
                    self.general_map_class(
                        "Unrecognized enum value(s)",
                        df,
                        class_name,
                        True,
                        None,
                        None,
                        None,
                    )
                elif clean_name == "format_columns":
                    df = self.clean_format_columns(
                        df, class_name, format_columns_options=clean_params
                    )
                elif clean_name == "remove_unknown_columns":
                    df = self.clean_remove_unknown_columns(df, class_name)

        # Save to disk
        if output_file is not None:
            logger.debug(f"Saving fixed data to {output_file}")
            save_data_frame(df, output_file, index=False)

        return output_file, df

    def clean_data(
        self,
        data_files: Dict[str, List[Union[str, Path, Dict]]],
        data_frames: Dict[str, List[pd.DataFrame]],
        output_dir: Union[str, Path],
        clean_operations: List[Dict[str, Any]],
        max_rows: int = 0,
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[pd.DataFrame]]]:
        """Clean all data files and DataFrames and optionally save the cleaned data to the specified output
        directory, ensuring that all output files names are unique and no existing file in output_dir is modified.

        Cleaning involve making sure columns are capitalized correctly, and making sure enumerations are capitalized
        correctly, and possibly other operations.

        Args:
            data_files (List[Union[str, Path, Dict]]]): Dictionary of all data files to clean. The keys are
                the class names and the values are lists of file paths belonging to that class or dictionaries
                specifying the Excel file and sheet name to load (In the format
                {EXCEL_FILE_KEY: "file.xlsx", EXCEL_SHEET_KEY: "sheet_name"}). Both data_files and data_frames are cleaned.
            data_frames (Dict[str, List[pd.DataFrame]]): Dictionary of all DataFrames to clean. The keys are
                the class names and the values are lists of DataFrames belonging to that class. Both data_files
                and data_frames are cleaned.
            output_dir (Union[str, Path]): Output directory to save the cleaned data files to. To avoid overwriting
                files in data_files that have the same name, we ensure that all output files have unique file names.
                The returned dictionary will contain the updated file name, if a file name is changed.
                If output_dir is None then the cleaned data is not saved to disk, and the cleaned DataFrames
                are returned.
            clean_operations (List[Dict[str, Any]]): List of operations to perform. Each item in the list is a dictionary where the
                key specifies which cleaning operation to  perform and teh values are the parameters for the operation.
                The type of the parameters depends on which operation it is. The available operations are:
                    correct_enums (bool):
                        If True then correcting capitalization and whitespace of enumerations. Defaults to False.
                    format_columns (Optional[Union[str, List[str]]]):
                        A single (str) or multiple (List[str]) operations to perform on the column names of the DataFrames.
                        Formating operations that can be performed are:
                                "lowercase": Make lowercase.
                                "uppercase": Make uppercase.
                                "alpha_numeric_underscore": Replace non alpha-numeric values with underscores.
                                "single_underscores": Replace double (or more) underscores (eg. __, ___) with single underscores
                                "trim_whitespace": Remove leading and trailing whitespace.
                                "trim_trailing_underscores": Remove trailing underscores.
                                "remove_chars": Remove all the specified characters. This should be specified as either a JSON/YAML
                                    string or as a dictionary of the form { "remove_chars": "abc" } where "abc" contains all the
                                    characters to remove (ie. "a", "b", and "c" will be removed).
                                "remove_special": Remove all special characters (characters other than alpha-numeric and spaces).
                        Multiple operations can be specified, and the operations are performed in the same order as specified
                        in the list. Defaults to None.
                    remove_unknown_columns (bool):
                        If True then remove columns that are not part of the class that the DataFrame belongs to, and are not a tracking slot.
                        Defaults to False.
            max_rows (int): Maximum number of rows to load and clean for each file. If 0 then clean all rows.
                Defaults to 0.

        Returns:
            Tuple[Dict[str, List[str]], Dict[str, List[pd.DataFrame]]]: A tuple of [cleaned_data_files, cleaned_data_frames]:
                cleaned_data_files: Dictionary of all outputed cleaned data files. The keys are the class name
                    the file belongs to and the values are lists of files. If output_dir is None then data_files will be
                    None (ie. no data saved to disk), instead see expanded_data_frames.
                cleaned_data_frames: Dictionary of all cleaned DataFrames. The keys are the class names and the
                    values are lists of cleaned DataFrames.
        """
        output_data_files = {}
        output_data_frames = {}

        total = (len(data_files) if data_files else 0) + (
            len(data_frames) if data_frames else 0
        )
        progress = ProgressCounter({CLEAN_BARID: total}, multiple_bars=False)

        with progress:
            # Loop through all data_files and data_frames
            for all_data in [data_files, data_frames]:
                if not all_data:
                    continue
                for class_name, sub_data in all_data.items():
                    if class_name not in output_data_files:
                        output_data_files[class_name] = []
                    if class_name not in output_data_frames:
                        output_data_frames[class_name] = []
                    # sub_data is either a list of files or a list of DataFrames
                    for data in sub_data:
                        data_file = data if not isinstance(data, pd.DataFrame) else None
                        data_frame = data if isinstance(data, pd.DataFrame) else None
                        assert (data_file is None) != (data_frame is None)

                        # Determine the output_file
                        if output_dir is not None:
                            if data_file:
                                if isinstance(data_file, Dict):
                                    basename = os.path.basename(
                                        data_file[EXCEL_FILE_KEY]
                                    )
                                    basename = "{class_name}({basename}).csv".format(
                                        class_name=class_name,
                                        basename=os.path.splitext(basename)[0],
                                    )
                                else:
                                    basename = os.path.basename(data_file)
                                output_file = os.path.join(output_dir, basename)
                            else:
                                output_file = os.path.join(
                                    output_dir, f"{class_name}.csv"
                                )
                            # Make sure the output file doesn't already exist
                            output_file = get_unique_output_file(output_file)
                        else:
                            output_file = None

                        # Clean the data
                        output_file, output_data_frame = self.clean_single_data(
                            data_file=data_file,
                            data_frame=data_frame,
                            output_file=output_file,
                            class_name=class_name,
                            max_rows=max_rows,
                            clean_operations=clean_operations,
                        )

                        # Keep the cleaned data for returning
                        output_data_files[class_name].append(
                            Path(output_file) if output_file else None
                        )
                        output_data_frames[class_name].append(output_data_frame)
                        progress.update(CLEAN_BARID, 1)

        self.output_all_log(clear=True)
        return output_data_files, output_data_frames
