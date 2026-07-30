"""
Class for cleaning data.

The cleaning options are specified with the clean_operations parameters of the functions clean_data and clean_single_data. It is
dictionary where the keys are the cleaning option names and the values are the parameters for the option. The type of the
parameters depend on the option. See the clean_data function for a list of options and their parameters.
"""

import os
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pandas as pd
import yaml
from linkml_runtime import SchemaView
from linkml_runtime.linkml_model.meta import EnumDefinition

from odm_map.progress import ProgressCounter
from odm_map.utils.extra_and_tracking_slots import is_extra_or_tracking_slot
from odm_map.utils.general_utils import (
    EXCEL_FILE_KEY,
    make_multivalued,
    read_data_frame,
    save_data_frame,
)
from odm_map.utils.logger import get_logger
from odm_map.utils.schema_caster import SchemaCaster
from odm_map.utils.schema_utils import (
    all_classes_without_tree_root,
    get_ranges_of_slot,
)

logger = get_logger(__name__)

# Title/ID of the progress bar for the cleaning
CLEAN_BARID = "Cleaning Data"


# Some standard column names to use in the output log files. We can also use column names
# not found here. The can be specified in the calls to add_to_log
class LogColumns:
    COUNT = "count"
    ROW = "row"
    CLASS_NAME = "table"
    SLOT_NAME = "column"
    VALUE = "value"
    NEW_VALUE = "newValue"
    NOTES = "notes"
    NEW_SLOT_NAME = "newColumn"


# Different log keys. Each represents a different log file/Excel tab. We generally use the values
# here as log_key values, but logging (ie. via add_to_log and other functions) will work for
# values not found here as well, and will be automatically saved to disk.
class Logs:
    UNKNOWN_ENUMS = "Unrecognized enum values"
    MISMATCH_PATTERN = "Mismatch pattern"
    ADD_ONTOLOGY_IDS = "Added ontology IDs"
    CORRECT_CAPS_AND_SPACING = "Correct caps and spacing"
    COLUMN_NAME_CHANGE = "Column name changes"
    COLUMN_REMOVED = "Columns removed"
    COLUMNS_MISSING = "Columns missing"


# Maximum length of a log key. These keys are used as either file names or Excel tab names. Excel tabs
# must have length 31 or less.
MAX_LOG_KEY_LENGTH = 31


class DataCleaner:
    def __init__(
        self,
        schema: str | Path | SchemaView | None = None,
    ):
        # Log lines (that have not yet been converted to a DataFrame). The rows for a log_key are the list of
        # values at self.log_lines[log_key]
        self.log_lines = {}
        # Log DataFramnes. After creating self.log_lines, we can convert them to DataFrames and are then stored
        # at self.log_dfs[log_key]. We only convert to DataFrames by calling move_log_lines_to_dfs(log_key), this
        # is much faster than appending to the DataFrame each time a single log line is added.
        self.log_dfs = {}
        # The location of the log file, set in clean_data
        self.log_file = None

        if isinstance(schema, (str, Path)):
            self.schema = SchemaView(schema)
        else:
            self.schema = schema

    def save_logs(self):
        """Save all logs to the log file.

        This will also clear the log stored in memory.
        """
        for log_key in list(self.log_lines.keys()):
            self.move_log_lines_to_dfs(log_key)

        if self.log_file:
            if os.path.dirname(self.log_file):
                os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

            # Order the reports according to the order in Logs
            reports = [getattr(Logs, f) for f in Logs.__dict__ if not f.startswith("_")]
            # Add the reports not found in Logs to the end
            reports = reports + [r for r in self.log_dfs if r not in reports]
            # Select all the reports in the order found in the variable reports
            reports = {r: self.log_dfs[r] for r in reports if r in self.log_dfs}
            # Remove empty reports
            reports = {r: df for r, df in reports.items() if len(df) > 0}

            if len(reports) > 0:
                # Sort by columns
                for sheet_name, df in reports.items():
                    sort_columns = [
                        LogColumns.CLASS_NAME,
                        LogColumns.SLOT_NAME,
                        LogColumns.ROW,
                    ]
                    sort_columns = [c for c in sort_columns if c in df.columns]
                    if sort_columns:
                        df = df.sort_values(sort_columns)
                        reports[sheet_name] = df

            if len(reports) == 0:
                # If there is no report, then create a single report that says "Nothing to report"
                reports["empty"] = pd.DataFrame({"log": ["Nothing to report"]})
            if os.path.splitext(self.log_file)[1].lower() == ".csv":
                # For CSV files, format the string self.log_file with log_name. Make a separate
                # log file for each log name.
                for log_name, df in reports.items():
                    log_name = re.sub("[^A-Za-z0-9]", "_", log_name.lower())
                    output_file = self.log_file.format(log_name=log_name)
                    df.to_csv(output_file, index=False)
            else:
                # For Excel file, each log gets its own tab
                with pd.ExcelWriter(self.log_file) as xl:
                    for log_name, df in reports.items():
                        df.to_excel(xl, sheet_name=log_name, index=False)

            total_rows = sum([len(df) for df in reports.values()])
            logger.info(
                f"There are {total_rows} messages in the log file: {self.log_file}"
            )

        # Reset the logs
        self.log_lines = {}
        self.log_dfs = {}

    def clean_format_and_match_columns(
        self,
        df: pd.DataFrame,
        class_name: str,
        format_columns_options: str | list[str],
    ) -> pd.DataFrame:
        """Cleaning operation to format all column names and then match them to valid columns found in the schema.
        Once formatting is complete, we try to match them, ignoring case. See DataCleaner.clean_data for all available
        cleaning options (specified with the "format_and_match_columns" clean_option).

        Args:
            df (pd.DataFrame): The DataFrame to clean the column names of. A copy of this DataFrame is made and
                the original is left unchanged.
            class_name (str): The class name that the DataFrame belongs to. It must exist in the schema for the DataCleaner.
            format_columns_options (str | list[str]): The formatting operations top apply to the column names.
                See clean_data for a list of all available formatting options (specified with the "format_and_match_columns"
                clean_option).

        Returns:
            pd.DataFrame: The DataFrame with the column names formatted.
        """
        if class_name not in all_classes_without_tree_root(self.schema):
            logger.debug(
                f"Not cleaning columns for class {class_name} since class is not recognized"
            )
            return df

        df = df.copy()

        if isinstance(format_columns_options, str):
            format_columns_options = [format_columns_options]

        class_defn = self.schema.induced_class(class_name)
        recognized_columns = [attr for attr in class_defn.attributes]
        lowercase_recognized_columns = [c.lower() for c in recognized_columns]

        columns = []
        # Schema columns that have already been claimed by a previous source column, and a
        # map of {source column index: schema column it duplicates} for columns dropped
        # because they duplicate an already-claimed schema column.
        claimed_columns = set()
        duplicate_indices = {}
        for idx, val in enumerate(df.columns):
            if is_extra_or_tracking_slot(val):
                columns.append(val)
                continue
            if isinstance(format_columns_options, (list, tuple)):
                for options in format_columns_options:
                    if isinstance(options, str):
                        options = yaml.safe_load(options)
                        if isinstance(options, str):
                            options = {options: True}
                    for option, param in options.items():
                        if option == "lowercase":
                            val = val.lower()
                        elif option == "uppercase":
                            val = val.upper()
                        elif option == "alpha_numeric_underscore":
                            val = re.sub("[^A-Za-z0-9]", "_", val)
                        elif option == "single_underscores":
                            val = re.sub("__+", "_", val)
                        elif option == "trim_trailing_underscores":
                            val = val.rstrip("_")
                        elif option == "trim_whitespace":
                            val = re.sub(r"^\s*", "", val)
                            val = re.sub(r"\s*$", "", val)
                        elif option == "remove_chars":
                            for ch in param:
                                val = val.replace(ch, "")
                        elif option == "remove_special":
                            val = re.sub(r"[^A-Za-z0-9\s]", "", val)
                        else:
                            raise ValueError(
                                f"Unrecognized format_and_match_columns option: {option}"
                            )
            # Once the column is formatted we try to convert it to the correct name as found
            # in the schema. An empty name (eg. a column formatted away to "") is treated as
            # unrecognized.
            if not val or val.lower() not in lowercase_recognized_columns:
                val = None
            else:
                val = recognized_columns[
                    lowercase_recognized_columns.index(val.lower())
                ]
                # Two source columns can normalize to the same schema column. Keep the
                # first one and drop later duplicates so we don't create duplicate
                # column labels (which would make later df[...] selection ambiguous).
                if val in claimed_columns:
                    duplicate_indices[idx] = val
                    val = None
                else:
                    claimed_columns.add(val)
            columns.append(val)

        # Add all the changes to the log files. Note that we are mapping df.columns[idx] to
        # the new values at columns[idx]. If columns[idx] is None then it's because the
        # column at that index is not a valid column name in the schema (or it's a
        # tracking/extra slot)
        for idx, (orig_column, new_column) in enumerate(zip(df.columns, columns)):
            if orig_column != new_column:
                if idx in duplicate_indices:
                    self.add_to_log(
                        Logs.COLUMN_REMOVED,
                        {
                            LogColumns.CLASS_NAME: class_name,
                            LogColumns.SLOT_NAME: orig_column,
                            LogColumns.NEW_SLOT_NAME: duplicate_indices[idx],
                            LogColumns.NOTES: "Column duplicates an already-matched column and removed",
                        },
                    )
                elif new_column is None:
                    self.add_to_log(
                        Logs.COLUMN_REMOVED,
                        {
                            LogColumns.CLASS_NAME: class_name,
                            LogColumns.SLOT_NAME: orig_column,
                            LogColumns.NOTES: "Column unrecognized and removed",
                        },
                    )
                else:
                    self.add_to_log(
                        Logs.COLUMN_NAME_CHANGE,
                        {
                            LogColumns.CLASS_NAME: class_name,
                            LogColumns.SLOT_NAME: orig_column,
                            LogColumns.NEW_SLOT_NAME: new_column,
                            LogColumns.NOTES: "Column renamed to recognized column",
                        },
                    )

        # Keep the column df.columns[idx] if columns[idx] is not None
        retain_columns = [
            df.columns[idx] for idx in range(len(columns)) if columns[idx] is not None
        ]
        df = df[retain_columns]

        # Rename the old column names to the new column names
        new_columns = [c for c in columns if c is not None]
        df.columns = new_columns

        # Add columns that are in the schema but are not found in the DataFrame (set their
        # values to None)
        missing_columns = [c for c in recognized_columns if c not in df.columns]
        df[missing_columns] = None
        for c in missing_columns:
            self.add_to_log(
                Logs.COLUMNS_MISSING,
                {
                    LogColumns.CLASS_NAME: class_name,
                    LogColumns.SLOT_NAME: c,
                    LogColumns.NOTES: "Column missing in dataset and treated as NULL",
                },
            )

        return df

    def add_to_log(
        self,
        log_key: str,
        log_lines: list[dict[str, Any]] | dict[str, Any],
    ):
        """Add the specified log lines to the log with the specified log key.

        Args:
            log_key (str): The log key to add the log lines to. Usually a value from class Logs.
                This becomes the tab name in the Excel log file, or a file name if saving as
                a CSV. Must be at most 31 characters.
            log_lines (list[dict[str, Any]] | dict[str, Any]): One or more lines to add
                to the log. If a dictionary then it is a single log line. If a list then it
                is multiple dictionaries where each dictionary is an individual line. Any number
                and value of keys can included in the dictionaries. The keys become the columns
                in the outputed log file.

        Raises:
            ValueError: The log_key is more than 31 characters long.
        """
        if len(log_key) > MAX_LOG_KEY_LENGTH:
            raise ValueError(
                f"Log key must be {MAX_LOG_KEY_LENGTH} characters or less: {log_key}"
            )
        if isinstance(log_lines, dict):
            log_lines = [log_lines]
        if log_key not in self.log_lines:
            self.log_lines[log_key] = []
        self.log_lines[log_key].extend(log_lines)

    def move_log_lines_to_dfs(self, log_key: str) -> pd.DataFrame:
        """Move all the log lines (which are dictionaries) that have been added with self.add_to_log to
        the DataFrame containing the actual log. This will also clear the log lines so that we can
        continue adding more lines with self.add_to_log.

        We usually want to add individual log lines with self.add_to_log, and only after adding a
        lot of them should we convert them to a DataFrame. It is much faster this way.

        This should also be called once after all logging is complete (ie. immediately before
        saving the log DataFrames to disk).

        Args:
            log_key (str): The log ID/key to convert the log lines to a DataFrame.

        Raises:
            ValueError: The log key was longer than 31 characters long.

        Returns:
            pd.DataFrame: The DataFrame consisting of the new log lines added to the log
                DataFrame. This does not contain the values moved with a previous call to
                move_log_liens_to_dfs, instead it only contains the new ones that were
                added. If no lines were added then None is returned.
        """
        if len(log_key) > MAX_LOG_KEY_LENGTH:
            raise ValueError(
                f"Log key must be {MAX_LOG_KEY_LENGTH} characters or less: {log_key}"
            )

        if log_key not in self.log_lines:
            return None

        # Convert the log lines to a DataFrame, then delete the lines in self.log_lines[log_key]
        df = pd.DataFrame(self.log_lines[log_key])
        del self.log_lines[log_key]

        if len(df):
            # Output a message saying there were log messages
            all_classes = ""
            if LogColumns.CLASS_NAME in df.columns:
                all_classes = sorted(df[LogColumns.CLASS_NAME].unique())
                all_classes = [f"'{c}'" for c in all_classes]
                joined_classes = ", ".join(all_classes)
                all_classes = (
                    f" in class{'' if len(all_classes) == 1 else 'es'} {joined_classes}"
                )
            logger.info(
                f"There are {len(df)} messages reported for '{log_key}'{all_classes}. Please view the log file for details: {self.log_file}"
            )

        # Append the new DataFrame of log lines to the existing log at self.log_dfs[log_key]
        if log_key not in self.log_dfs:
            self.log_dfs[log_key] = pd.DataFrame()
        log_df = self.log_dfs[log_key]
        log_df = pd.concat([log_df, df], ignore_index=True)
        self.log_dfs[log_key] = log_df

        return df

    def general_map_slot(
        self,
        log_note: str,
        log_key: str,
        df_column: pd.Series,
        class_name: str,
        slot_name: str,
        source_values: list[str],
        target_values: list[str],
        can_be_anything: bool,
        log_unknown_values: bool = False,
        clear_unknown_values: bool = False,
        source_value_formatter: Callable[[str], str] | None = None,
    ) -> pd.Series:
        """A general cleaning function for cleaning a single slot in a class. This is called by self.general_map_class.

        It works by performing a simple mapping from source_values[idx] to target_values[idx]. In general, given a value
        v in the slot, the value gets mapped to target_values[source_values.index(source_valu_formatter(v))].

        A log of mapped values is retained in the log with key log_key. If log_unknown_values is True then values
        that are unrecognized (ie. not in source_values) is logged to the log with key Logs.UNKNOWN_ENUMS.

        Args:
            log_note (str): A descriptive title of the cleaning operation, such as "Added ontology IDs". This is used to
                report the results to the user in the log file (in the field LogColumns.NOTES).
            log_key (str): Log changes made to the log with this key. Must be at most 31 characters.
            df_column (pd.Series): The column that we are cleaning. This is the column taken from the class named
                class_name and the slot named slot_name. A copy will be made and modified, with the original left
                unchanged.
            class_name (str): The name of the class that df_column belongs to.
            slot_name (str): The slot (in class class_name) that df_column represents.
            source_values (list[str]): The mapping source values. The mapping performed is target_values[source_values.index(v)]
            target_values (list[str]): The mapping target values. The mapping performed is target_values[source_values.index(v)]
            can_be_anything (bool): If True, then the values in the slot can take on any value. It is usually set to
                True if the slot has at least one range that is not an enumeration. If False then if a value in the slot
                is not found in source_values, then it is counted as an invalid value and stored and reported in
                the Logs.UNKNWON_ENUMS log (if log_unknown_values is True).
            log_unknown_values (bool): If True then log unrecognized values (ie that do not match a value in
                source_values) as an unrecognized enumeration value to the Logs.UNKNOWN_ENUMS log.
                Defaults to False.
            clear_unknown_values (bool): If True then any source value that is unrecognized (ie. is not found
                in source_values) gets cleared in df_column (set to None). If False then unrecognized source
                values are left unchanged. Defaults to False.
            source_value_formatter (Callable[[str], str] | None, optional): Function that formats all the source values
                within df_column before trying to map (from source_values[idx] to target_values[idx]). If None then the
                default behavior is to use the source values unchanged when mapping.

        Returns:
            pd.Series: A copy of the column df_column with all the cleaning/mapping performed according to
                the parameters.
        """
        if class_name not in all_classes_without_tree_root(self.schema):
            logger.debug(
                f"Skipping '{log_note}' for class {class_name} since class is not recognized"
            )
            return df_column

        df_column = df_column.copy()
        slot_defn = self.schema.induced_slot(slot_name, class_name)

        if source_value_formatter is None:
            # Use the default source_value_formatter, which is to return the value unchanged
            def _mirror_value(v):
                return v

            source_value_formatter = _mirror_value

        def _get_mapped_value(row_idx: int, v: Any) -> str:
            """Map the value v to a new value.

            We first format the value with source_value_formatter. Then find the index of the
            value in the list source_values. If it is found in source_values, we get its index
            (idx) then map it to target_values[idx].

            If the slot for the class_name/slot_name is multivalued, then a list of mapped values
            is returned. Otherwise a single value is returned.

            Args:
                row_idx (int): The row in the source file that the value came from. This is
                    for logging purposes.
                v (Any): The value to map.

            Returns:
                str: The mapped value. If the value can't be mapped (ie. after calling source_value_formatter
                    it cannot be found in the list source_values), then None is returned.
            """
            return_first_element = False
            if slot_defn.multivalued:
                v = make_multivalued(v)
            elif not isinstance(v, (list, tuple)):
                v = [v]
                return_first_element = True
            for v_idx in range(len(v)):
                old_v = v[v_idx]
                if not pd.isna(old_v):
                    old_v = str(old_v)
                try:
                    source_v = source_value_formatter(old_v)
                    idx = source_values.index(source_v)
                    new_v = target_values[idx]
                    v[v_idx] = new_v
                    if new_v != old_v:
                        # Add the class name, slot name, original value, new value to the log
                        self.add_to_log(
                            log_key,
                            {
                                LogColumns.CLASS_NAME: class_name,
                                LogColumns.SLOT_NAME: slot_name,
                                LogColumns.VALUE: old_v,
                                LogColumns.NEW_VALUE: new_v,
                                LogColumns.ROW: row_idx + 1,
                                LogColumns.NOTES: log_note,
                            },
                        )
                # ValueError: the (formatted) value is not in source_values (an unknown enum).
                # AttributeError: the value is NaN, so the string formatter (eg. .lower()) fails.
                # Both mean the value cannot be mapped; other exceptions are real bugs and propagate.
                except (ValueError, AttributeError):
                    if not can_be_anything:
                        # Add the class name, slot name, original value to the log of unknown enum values.
                        # If the original value (old_v) is empty and the slot is not required then an empty
                        # value is allowed
                        if clear_unknown_values:
                            v[v_idx] = None
                        if log_unknown_values and (
                            (not pd.isna(old_v) and old_v != "") or slot_defn.required
                        ):
                            self.add_to_log(
                                Logs.UNKNOWN_ENUMS,
                                {
                                    LogColumns.CLASS_NAME: class_name,
                                    LogColumns.SLOT_NAME: slot_name,
                                    LogColumns.VALUE: old_v,
                                    LogColumns.ROW: row_idx + 1,
                                    LogColumns.NOTES: "Unrecognized enum values",
                                },
                            )
            if slot_defn.multivalued:
                return v
            return v[0] if return_first_element else v

        # Perform the cleaning, by mapping from source_values[idx] to target_values[idx]
        df_column = pd.Series(
            [_get_mapped_value(idx, val) for idx, val in df_column.items()],
            index=df_column.index,
            name=df_column.name,
        )

        return df_column

    def check_patterns(self, df: pd.DataFrame, class_name: str):
        """Check that all values in the DataFrame conform to the pattern specified in the schema for each slot.

        Args:
            df (pd.DataFrame): The DataFrame to check.
            class_name (str): The class name that the DataFrame belongs to.
        """
        if class_name not in all_classes_without_tree_root(self.schema):
            logger.debug(
                f"Skipping 'Check Patterns' for class {class_name} since class is not recognized"
            )
            return

        class_defn = self.schema.induced_class(class_name)
        for slot_name in df.columns:
            if slot_name not in class_defn.attributes:
                continue

            # Get the regex pattern from the schema that we need to match
            slot_defn = self.schema.induced_slot(slot_name, class_name)
            pattern = slot_defn.pattern
            if pattern is None:
                continue

            # Vectorise the fullmatch check; only iterate the (typically rare) mismatches
            non_null = df[slot_name].dropna()
            str_col = non_null.astype(str)
            mismatches = str_col[~str_col.str.fullmatch(pattern)]
            for idx, str_value in mismatches.items():
                self.add_to_log(
                    Logs.MISMATCH_PATTERN,
                    {
                        LogColumns.CLASS_NAME: class_name,
                        LogColumns.SLOT_NAME: slot_name,
                        LogColumns.VALUE: str_value,
                        LogColumns.ROW: idx + 1,
                        LogColumns.NOTES: f"Values do not match pattern {pattern}",
                    },
                )

    def general_map_class(
        self,
        log_note: str,
        log_key: str,
        df: pd.DataFrame,
        class_name: str,
        get_source_values: Callable[[EnumDefinition], str],
        get_target_values: Callable[[EnumDefinition], str],
        source_value_formatter: Callable[[str], str] | None,
        log_unknown_values: bool = False,
        clear_unknown_values: bool = False,
    ) -> pd.DataFrame:
        """A general cleaning operation to be called for each class that we want to clean. It works by mapping values
        from source to target values. First, the input value is formatted with source_value_formatter. If the
        formatted value is found in the values returned by get_source_values (which is applied to the enum
        for the source slot), then its index in get_source_values is retrieved, and the value it gets mapped
        to is the same index in get_target_values.

        Note that this function works by calling self.general_map_slot(...) on all enum slots in the class.

        Args:
            log_note (str): A descriptive title of the cleaning operation, such as "Added ontology IDs". This is used to
                report the results to the user in the log file (in the field LogColumns.NOTES).
            log_key (str): Log changes made to the log with this key. Must be at most 31 characters.
            df (pd.DataFrame): The DataFrame for the class. A copy is made and modified (and returned), with the original
                value left unchanged.
            class_name (str): The name of the class that the DataFrame belongs to.
            get_source_values (Callable[[EnumDefinition], str]): Function that takes an EnumDefinition as a parameter and
                returns a list of source values for mapping for the enum. For a given enum, get_source_values(enum)[idx]
                maps to get_target_values(enum)[idx]. If get_source_values is None, then the default will be to return
                all permissible values of the enum (ie. list(enum.permissible_values.keys()))
            get_target_values (Callable[[EnumDefinition], str]): Function that takes an EnumDefinition as a parameter and
                returns a list of target values for mapping for the enum. For a given enum, get_source_values(enum)[idx]
                maps to get_target_values(enum)[idx]. If get_target_values is None, then the default will be to return
                all permissible values of all the enums (ie. list(enum.permissible_values.keys()))
            source_value_formatter (Callable[[str], str] | None, optional): Function that formats all the source values
                within the slots of the DataFrame before trying to map (from get_source_values(enum)[idx] to
                get_target_values(enum)[idx]). If None then the default behavior is to use the source values unchanged when
                mapping.
            log_unknown_values (bool): If True then log unrecognized values (ie that do not match a value in
                source_values) to the Logs.UNKNOWN_ENUMS log. Defaults to False.
            clear_unknown_values (bool): If True then any source value that is unrecognized (ie. is not found
                in source_values) gets cleared in df (set to None). If False then unrecognized source
                values are left unchanged. Defaults to False.

        Returns:
            pd.DataFrame: A copy of df with all the slots that are enumerations cleaned according to the parameters.
        """
        df = df.copy()

        def _get_enum_permissible_values(enum: EnumDefinition) -> list[str | None]:
            # By default, the get_source_values and get_target_values functions simply returns the EnumDefinition's permissible values
            # unchanged
            return list(enum.permissible_values.keys())

        if get_source_values is None:
            get_source_values = _get_enum_permissible_values
        if get_target_values is None:
            get_target_values = _get_enum_permissible_values

        class_defn = self.schema.induced_class(class_name)

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
                    log_note=log_note,
                    log_key=log_key,
                    df_column=df[slot_name],
                    class_name=class_name,
                    slot_name=slot_name,
                    source_values=source_values,
                    target_values=target_values,
                    can_be_anything=can_be_anything,
                    source_value_formatter=source_value_formatter,
                    log_unknown_values=log_unknown_values,
                    clear_unknown_values=clear_unknown_values,
                )

        return df

    def clean_single_data(
        self,
        data_file: str | Path | dict | None,
        data_frame: pd.DataFrame | None,
        output_file: str | Path | None,
        class_name: str,
        clean_operations: list[dict[str, Any]],
        max_rows: int | None = 0,
    ) -> tuple[str, pd.DataFrame]:
        """Clean either a single data file or a single DataFrame.

        Args:
            data_file (str | Path | dict | None): The file to clean. If a dictionary, then it is for an
                Excel file in the format {EXCEL_FILE_KEY: "file.xlsx", EXCEL_SHEET_KEY: "sheet_name"}. If specified then
                data_frame must be None.
            data_frame (pd.DataFrame | None): The DataFrame to clean. If specified then data_file must be None.
            output_file (str | Path | None): The file to save the cleaned data to. This should
                be different than the input_file to avoid overwriting the original. If None then the cleaned
                data is not saved to disk, but the cleaned DataFrame is still returned.
            class_name (str): The class name that the data_file or data_frame is for. This should be a class name found in
                the schema.
            clean_operations (list[dict[str, Any]]): List of dictionaries specifying all the cleaning operations to perform.
                The key of each dictionary specifies which operation to perform and the value is the parameters for that
                operation. The operations are performed in the same order as they appear in the list. See clean_data for all
                available operations
            max_rows (int | None): Maximum number of rows to clean from the file or DataFrame. The returned DataFrame
                and save data will have at most this many rows. If 0 or None then clean all rows. Defaults to 0.

        Raises:
            ValueError: An invalid cleaning operation was found, or an invalid parameter for a cleaning operation
                was found.

        Returns:
            tuple[str, pd.DataFrame]: A tuple of (new file name, data frame). The DataFrame
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

            # Cast all columns to correct type, according to the schema
            caster = SchemaCaster(self.schema)
            caster.cast_df(df, class_name)
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

                    def _get_source_values(enum: EnumDefinition) -> list[Any]:
                        # Get all permissible values of the enum, with multiple consecutive
                        # spaces reduced to one space, and the value made lowercase.
                        return [
                            re.sub("  +", " ", v.lower())
                            for v in list(enum.permissible_values.keys())
                        ]

                    df = self.general_map_class(
                        log_note="Corrected capitalization and spacing",
                        log_key=Logs.CORRECT_CAPS_AND_SPACING,
                        df=df,
                        class_name=class_name,
                        get_source_values=_get_source_values,
                        get_target_values=None,
                        source_value_formatter=_lowercase_minimize_spacing,
                        log_unknown_values=True,
                        clear_unknown_values=True,
                    )
                elif clean_name == "add_ontology_ids_to_enums" and clean_params:
                    if not isinstance(clean_params, dict) or not isinstance(
                        clean_params.get("match_ontology_id", None), str
                    ):
                        raise ValueError(
                            "Parameter 'match_ontology_id' for action 'add_ontology_ids_to_enums' in config file must exist and be a string."
                        )

                    match_ontology_id = clean_params["match_ontology_id"]

                    def _search_and_remove(
                        v: str, match_ontology_id: str = match_ontology_id
                    ) -> str | None:
                        # From v remove the ontology ID (and strip and lowercase).
                        # If v does not have an ontology ID then return None.
                        res = re.search(match_ontology_id, v.strip())
                        if res is None:
                            return None
                        span = res.span(0)
                        v = v[: span[0]] + v[span[1] :]
                        return v.strip().lower()

                    def _get_source_values(enum: EnumDefinition) -> list[Any]:
                        # Remove the ontology ID from the permissible values
                        vals = [
                            _search_and_remove(v)
                            for v in list(enum.permissible_values.keys())
                        ]
                        return vals

                    df = self.general_map_class(
                        log_note="Added ontology IDs",
                        log_key=Logs.ADD_ONTOLOGY_IDS,
                        df=df,
                        class_name=class_name,
                        get_source_values=_get_source_values,
                        get_target_values=None,
                        source_value_formatter=_lowercase_minimize_spacing,
                        log_unknown_values=False,
                        clear_unknown_values=False,
                    )
                elif clean_name == "format_and_match_columns":
                    if not isinstance(clean_params, bool) or clean_params:
                        df = self.clean_format_and_match_columns(
                            df, class_name, format_columns_options=clean_params
                        )
                elif clean_name == "check_patterns":
                    self.check_patterns(df, class_name)
                else:
                    raise ValueError(f"Unrecognized clean operation {clean_name}")

        # Save to disk
        if output_file is not None:
            logger.debug(f"Saving fixed data to {output_file}")
            save_data_frame(df, output_file, index=False)

        return output_file, df

    def clean_data(
        self,
        data_files: dict[str, list[str | Path | dict]],
        data_frames: dict[str, list[pd.DataFrame]],
        output_dir: str | Path,
        log_file: str | Path,
        clean_operations: list[dict[str, Any]],
        max_rows: int = 0,
    ) -> tuple[dict[str, list[str]], dict[str, list[pd.DataFrame]]]:
        """Clean all data files and DataFrames and optionally save the cleaned data to the specified output
        directory, ensuring that all output files names are unique and no existing file in output_dir is modified.

        Cleaning involve making sure columns are capitalized correctly, and making sure enumerations are capitalized
        correctly, and possibly other operations.

        Args:
            data_files (dict[str, list[str | Path | dict]]): Dictionary of all data files to clean. The keys are
                the class names and the values are lists of file paths belonging to that class or dictionaries
                specifying the Excel file and sheet name to load (In the format
                {EXCEL_FILE_KEY: "file.xlsx", EXCEL_SHEET_KEY: "sheet_name"}). Both data_files and data_frames are cleaned.
            data_frames (dict[str, list[pd.DataFrame]]): Dictionary of all DataFrames to clean. The keys are
                the class names and the values are lists of DataFrames belonging to that class. Both data_files
                and data_frames are cleaned.
            output_dir (str | Path): Output directory to save the cleaned data files to. To avoid overwriting
                files in data_files that have the same name, we ensure that all output files have unique file names.
                The returned dictionary will contain the updated file name, if a file name is changed.
                If output_dir is None then the cleaned data is not saved to disk, and the cleaned DataFrames
                are returned.
            log_file (str | Path): The Excel file to save the log of changes to. If None then no log file is saved.
            clean_operations (list[dict[str, Any]]): List of operations to perform. Each item in the list is a dictionary where the
                key specifies which cleaning operation to  perform and teh values are the parameters for the operation.
                The type of the parameters depends on which operation it is. The available operations are:
                    correct_enums (bool):
                        If True then correcting capitalization and whitespace of enumerations. Defaults to False.
                    format_and_match_columns (str | list[str] | None):
                        A single (str) or multiple (list[str]) operations to perform on the column names of the DataFrames.
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
                        in the list. Once formatting is complete, we then match the formatted names to valid column names in
                        the schema (ignoring case). If columns are found in the schema but missing in the DataFrame then
                        those columns are added (with None values). Defaults to None.
            max_rows (int): Maximum number of rows to load and clean for each file. If 0 then clean all rows.
                Defaults to 0.

        Returns:
            tuple[dict[str, list[str]], dict[str, list[pd.DataFrame]]]: A tuple of [cleaned_data_files, cleaned_data_frames]:
                cleaned_data_files: Dictionary of all outputed cleaned data files. The keys are the class name
                    the file belongs to and the values are lists of files. If output_dir is None then data_files will be
                    None (ie. no data saved to disk), instead see expanded_data_frames.
                cleaned_data_frames: Dictionary of all cleaned DataFrames. The keys are the class names and the
                    values are lists of cleaned DataFrames.
        """
        self.log_file = log_file

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
                        if not ((data_file is None) != (data_frame is None)):
                            raise ValueError(
                                f"Expected exactly one of data_file or data_frame to be set, got data_file={data_file!r}, data_frame={type(data_frame)}"
                            )

                        # Determine the output_file
                        if output_dir is not None:
                            if data_file:
                                if isinstance(data_file, dict):
                                    basename = os.path.basename(
                                        data_file[EXCEL_FILE_KEY]
                                    )
                                    basename = f"{class_name}({os.path.splitext(basename)[0]}).csv"
                                else:
                                    basename = os.path.basename(data_file)
                                output_file = os.path.join(output_dir, basename)
                            else:
                                output_file = os.path.join(
                                    output_dir, f"{class_name}.csv"
                                )
                            # Make sure the output file doesn't already exist
                            # output_file = get_unique_output_file(output_file)
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

        self.save_logs()
        return output_data_files, output_data_frames
