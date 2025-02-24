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
from typing import Tuple, List, Union, Optional, Dict, Any
import yaml

from linkml_runtime import SchemaView

from odm_map.utils.general_utils import (
    read_data_frame,
    save_data_frame,
    choose_ignore_case_value,
    get_unique_output_file,
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

    def remove_ontology_id(self, val: str) -> str:
        """Remove an ontology ID from the end of a value. For example, "degree Celsius (C) [UO:0000027]" would
            become "degree Celsius (C)"

        Args:
            val (str): The value to remove the ontology ID from.

        Returns:
            str: The value with the ontology ID removed. If there was no ontology ID it is returned unchanged.
        """
        val = re.sub(r"\[[A-Za-z0-9_]+:[A-Za-z0-9_]+\]$", "", val.strip()).strip()
        return val

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
                    if option == "trim_underscores":
                        val = val.strip("_")
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

    def clean_add_ontology_ids_to_enums(
        self, df: pd.DataFrame, class_name: str
    ) -> pd.DataFrame:
        """Add ontology IDs, if they exist, to all the enumeration values in the DataFrame.

        The ontology IDs are determined by the schema. They are the IDs in square brackets concatenated to
        the end of the enumeration value. For example, the enum value "degree Celsius (C) [UO:0000027]" has
        the ontology ID "UO:0000027". If we find the value "degree Celsius (C)" in the DataFrame, and the
        corresponding enumeration in the schema has a permissible value of "degree Celsius (C) [UO:0000027]",
        then the value in the DataFrame will be replaced with "degree Celsius (C) [UO:0000027]".

        Note that when trying to match a DataFrame enum value with a schema enum value that capitalization is
        ignored, and sequences of multiple spaces are replaced with single spaces when trying to match (but the
        resulting enum value has the same capitalization and spacing as the schema enum value).

        Args:
            df (pd.DataFrame): The DataFrame to add ontology IDs to. A copy of this DataFrame is made and
                the original left unchanged.
            class_name (str): The class name that the DataFrame belongs to. We will iterate over all columns
                in the schema that belong to this class.

        Returns:
            pd.DataFrame: The DataFrame with ontology IDs added.
        """
        if class_name not in all_classes_without_tree_root(self.schema):
            logger.debug(
                f"Not adding ontology IDs to enums for class {class_name} since class is not recognized"
            )
            return df

        logger.debug(f"Correcting capitalization for class {class_name}")
        df = df.copy()

        class_definition = self.schema.induced_class(class_name)

        def _get_onto_value(
            v, permissible_values: List[str], permissible_values_simplified: List[str]
        ) -> str:
            try:
                idx = permissible_values_simplified.index(re.sub("  +", " ", v.lower()))
                return permissible_values[idx]
            except Exception:
                return v

        # Go through all the columns in the DataFrame and add ontology IDs when appropriate
        for slot_name in df.columns:
            if slot_name not in class_definition.attributes:
                continue

            slot_ranges = get_ranges_of_slot(class_name, slot_name, self.schema)
            if slot_ranges:
                for slot_range in slot_ranges:
                    # Get enumeration for the slot range, if there is one.
                    enum = self.schema.all_enums().get(str(slot_range), None)
                    if enum is not None:
                        permissible_values = list(enum.permissible_values.keys())
                        # The "simplified" values are the permissible values with the ontology ID
                        # removed, the values in lowercase, and sequences of multiple spaces replaced
                        # with single spaces. This is used to match the enum values in the
                        # DataFrame, that are in lowercase and have multiple spaces removed (but
                        # the ontology ID, if there is one, is not removed)
                        permissible_values_simplified = [
                            re.sub("  +", " ", self.remove_ontology_id(v).lower())
                            for v in permissible_values
                        ]
                        df[slot_name] = df[slot_name].map(
                            lambda x: _get_onto_value(
                                x, permissible_values, permissible_values_simplified
                            )
                        )

        return df

    def clean_correct_enums(self, df: pd.DataFrame, class_name: str) -> pd.DataFrame:
        """Using the schema, correct the capitalization and whitespace of all enumeration values so that they
        match the capitalization and whitespace in the schema. If it is not a recognized enumeration value it is
        left unchanged.

        Args:
            df (pd.DataFrame): The DataFrame to correct. The original is left unchanged (a copy is returned).
            class_name (str): The class name of the table.

        Returns:
            pd.DataFrame: A copy of the DataFrame, with the enumeration value capitalization corrected.
        """
        if class_name not in all_classes_without_tree_root(self.schema):
            logger.debug(
                f"Not correcting enum capitalization for class {class_name} since class is not recognized"
            )
            return df

        logger.debug(f"Correcting capitalization for class {class_name}")
        df = df.copy()

        class_definition = self.schema.induced_class(class_name)

        # changes_history stores a count of the changes made to enumeration values to correct for capitalization.
        # The keys are the slot name, and the values are a sub dictionary. The keys of the sub dictionary
        # are the change string (in the form "origEnumValue -> fixedEnumValue") and the values are the
        # counts of how many times that change was made.
        changes_history = {}
        # unrecognized_history stores unrecognized enumeration values. The keys are the slot names, the values are
        # sub-dictionaries where the keys are the actual unrecognized enum values and the keys are the counts of how
        # many times that unrecognzied enum value occurs
        unrecognized_history = {}

        # Fix enumerations (Use correct capitalization), and only keep recognized slots
        for slot_name in df.columns:
            if is_extra_or_tracking_slot(slot_name):
                continue
            if slot_name not in class_definition.attributes:
                continue
            slot_ranges = get_ranges_of_slot(class_name, slot_name, self.schema)

            if slot_ranges:
                permissible_values = []

                can_be_anything = False
                for slot_range in slot_ranges:
                    # Get enumeration for the slot range, if there is one, and fix up the capitalization of all slot values.
                    enum = self.schema.all_enums().get(str(slot_range), None)
                    if enum is not None:
                        cur_permissible_values = list(enum.permissible_values.keys())
                        if len(cur_permissible_values) == 0:
                            can_be_anything = True
                        permissible_values += cur_permissible_values
                    else:
                        can_be_anything = True

                lowercase_permissible_values = [
                    re.sub("  +", " ", v.lower()) for v in permissible_values
                ]
                df_orig = df[slot_name].copy()
                replacements_df = df[slot_name].apply(
                    lambda x: choose_ignore_case_value(
                        re.sub("  +", " ", x) if isinstance(x, str) else x,
                        permissible_values,
                        lowercase_permissible_values,
                        return_same_if_missing=can_be_anything,
                    )
                )

                # Keep a history of which enum values are invalid. These are values where replacements_df
                # is None but the corresponding value in df[slot_name] was not empty.
                unrecognized_enums_filt = pd.isna(replacements_df) & (
                    ~pd.isna(df[slot_name]) | df[slot_name] != ""
                )
                if unrecognized_enums_filt.any():
                    if slot_name not in unrecognized_history:
                        unrecognized_history[slot_name] = {}
                    unrecognized_str = df[slot_name][unrecognized_enums_filt]
                    # Go through each unrecognized enum value and update the count of how many times it is found
                    for enum_value in unrecognized_str.unique():
                        if enum_value not in unrecognized_history[slot_name]:
                            unrecognized_history[slot_name][enum_value] = 0
                        unrecognized_history[slot_name][enum_value] += (
                            (unrecognized_str == enum_value)
                            | (pd.isna(enum_value) & pd.isna(unrecognized_str))
                        ).sum()
                    # Set the blank unrecognized values in replacements_df to the original enum value.
                    replacements_df[unrecognized_enums_filt] = df[slot_name][
                        unrecognized_enums_filt
                    ]

                df[slot_name] = replacements_df

                # Keep a history of which enum values were changed
                changes_filt = df_orig.map(lambda x: "" if pd.isna(x) else x) != df[
                    slot_name
                ].map(lambda x: "" if pd.isna(x) else x)
                if changes_filt.any():
                    # changes_str is "origEnumValue -> fixedEnumValue"
                    changes_str = (
                        df_orig[changes_filt].astype(
                            str
                        )  # .map(lambda x: str(type(x)))
                        + " -> "
                        + df[slot_name][changes_filt].astype(
                            str
                        )  # .map(lambda x: str(type(x)))
                    )
                    if slot_name not in changes_history:
                        changes_history[slot_name] = {}
                    slot_changes_history = changes_history[slot_name]
                    # Loop through all changes_str values, and increase the count for each
                    for change_key in changes_str:
                        if change_key not in slot_changes_history:
                            slot_changes_history[change_key] = 0
                        slot_changes_history[change_key] += 1

        # Report the capitalization changes to the user
        def _show_history(history: Dict[str, Dict[str, int]], msg: str):
            for slot_name, slot_history in history.items():
                for change_str, count in slot_history.items():
                    slot_history[change_str] = (
                        f"{count} time{'s' if count != 1 else ''}"
                    )
                slot_history = sorted(
                    [
                        f"{k if not pd.isna(k) and k != '' else '<empty>'} ({c})"
                        for k, c in slot_history.items()
                    ],
                    key=lambda x: str(x).lower(),
                )
                changes_str = make_logger_bullet_list(slot_history)
                cur_msg = msg.format(slot_name=slot_name, class_name=class_name)
                if changes_str:
                    self.add_to_log(
                        "warning",
                        f"{cur_msg}\n{changes_str}",
                    )

        _show_history(
            unrecognized_history,
            msg="The following invalid enumeration values were found in column '{slot_name}' of table '{class_name}', please consider correcting them:",
        )
        _show_history(
            changes_history,
            msg="The following enumeration values were automatically corrected for capitalization and spacing in column '{slot_name}' of table '{class_name}':",
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
                    df = self.clean_correct_enums(df, class_name)
                elif clean_name == "add_ontology_ids_to_enums" and clean_params:
                    df = self.clean_add_ontology_ids_to_enums(df, class_name)
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
                                "trim_underscores": Remove leading and trailing underscores.
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
