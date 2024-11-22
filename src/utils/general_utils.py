# %%
"""
General utility functions.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import os
from pathlib import Path
import pandas as pd
import yaml
import inspect
from typing import Union, List, Optional, Any, Dict, Callable
import re
import numpy as np

from linkml_runtime import SchemaView

from utils.logger import get_logger, make_logger_bullet_list
from utils.schema_utils import all_classes_without_tree_root
from utils.clean_exit_error import CleanExitError
from utils.tracking_slots import add_tracking_columns
from progress.progress_counter import ProgressCounter
from progress.empty_counter import EmptyCounter

EMPTY_PERMISSIBLE_VALUE = "<empty>"

RECOGNIZED_EXTENSIONS = [".tsv", ".txt", ".csv", ".yaml", ".yml"]

logger = get_logger(__name__)


def order_columns(df: pd.DataFrame, column_order: List[str]) -> pd.DataFrame:
    """Order the columns in a DataFrame.

    Args:
        df (pd.DataFrame): The DataFrame to order the columns of.
        column_order (List[str]): The order of the columns. Any column in df not found in this
            list are put at the end.

    Returns:
        pd.DataFrame: A copy of the DataFrame ordered by column.
    """
    columns = list(column_order) + [c for c in df.columns if c not in column_order]
    return df[columns].copy()


def save_data_frame(
    df: pd.DataFrame, output_file: Union[str, Path], strip: bool = True, **kwargs
):
    """Save a Pandas DataFrame to disk as a TSV, CSV, or YAML file.

    Args:
        df (pd.DataFrame): The DataFrame to save.
        output_file (Union[str, Path]): The output file to save to. Can have extension ".csv", ".tsv",
            ".txt", ".yaml", or ".yml". If the extension is ".tsv" or ".txt" then tab delimeters are used.
        strip (bool): If True then strip leading and trailing whitespace from all string values
            in the DataFrame. (Defaults to True)
        **kwargs: Additional key-word arguments to pass to df.to_csv for character-separated formats.
    """
    if strip:
        df = strip_whitespace(df)
    if os.path.dirname(output_file):
        os.makedirs(os.path.dirname(output_file), exist_ok=True)
    ext = os.path.splitext(output_file)[1]
    if ext in [".tsv", ".txt", ".csv"]:
        df.to_csv(output_file, sep="\t" if ext in [".tsv", ".txt"] else ",", **kwargs)
    elif ext in [".yaml", ".yml"]:
        with open(output_file, "w") as f:
            data = {c: list(df[c]) for c in df.columns}
            yaml.dump(data, f)
    else:
        raise ValueError(f"Extension not supported in save_data_frame: {output_file}")


def read_data_frame(file: str, **kwargs) -> pd.DataFrame:
    """Read a Pandas DataFrom from disk.

    Args:
        file (str): The file to read. Supports loading files with any of the extensions in RECOGNIZED_EXTENSIONS.
        **kwargs: Additional key-word arguments passed to pd.read_csv for character-separated file formats.

    Returns:
        pd.DataFrame: The DataFrame loaded from the file.
    """
    if isinstance(file, Dict):
        sheet_name = file["sheet"]
        file = file["excel_file"]

    ext = os.path.splitext(file)[1].lower()
    if ext in [".tsv", ".txt", ".csv"]:
        if ext in [".tsv", ".txt"]:
            sep = "\t"
        else:
            sep = ","
        df = pd.read_csv(
            file, sep=sep, low_memory=False, **select_func_kwargs(pd.read_csv, kwargs)
        )
    elif ext in [".yaml", ".yml"]:
        with open(file, "r") as f:
            data = yaml.safe_load(f)
        df = pd.DataFrame(data)
    elif ext in [".xlsx"]:
        df = pd.read_excel(
            file, sheet_name=sheet_name, **select_func_kwargs(pd.read_excel, kwargs)
        )
    else:
        raise CleanExitError(f"Unrecognized extension for file {file}")
    return df


def validate_columns_with_schema(
    df: pd.DataFrame,
    schema: Union[SchemaView, str, Path],
    class_name: str,
    file: Union[str, Path],
) -> List[str]:
    warning_log = []

    if isinstance(schema, (str, Path)):
        schema = SchemaView(schema)

    class_defn = schema.induced_class(class_name)

    # Check for missing required columns
    required_missing_attributes = sorted(
        [
            attr
            for attr, defn in class_defn.attributes.items()
            if attr not in df.columns and defn.required
        ],
        key=lambda x: str(x).lower(),
    )
    # Check for missing (but not required) columns
    not_required_missing_attributes = sorted(
        [
            attr
            for attr, defn in class_defn.attributes.items()
            if attr not in df.columns and not defn.required
        ],
        key=lambda x: str(x).lower(),
    )
    if required_missing_attributes or not_required_missing_attributes:
        # There are some missing attributes, tell the user
        missing_attributes = [
            f"{r} (REQUIRED)" for r in required_missing_attributes
        ] + not_required_missing_attributes
        missing_attributes_str = make_logger_bullet_list(missing_attributes)
        warning_log.append(
            f"The following columns are missing in table '{class_name}' and will be treated as blank from file {file}:\n{missing_attributes_str}"
        )

    # Check for extra unrecognized columns
    all_attributes = list(class_defn.attributes.keys())
    unrecognized_attributes = [
        attr for attr in df.columns if attr not in all_attributes
    ]
    if unrecognized_attributes:
        # Collect any recommended renaming of attributes (based purely on capitalization. eg. If
        # sampleID is a recognized attribute but the DataFrame has an attribute named SampleID, then
        # we will recommend to the user to rename it to sampleID)
        recommended = [
            choose_ignore_case_value(c, all_attributes, return_same_if_missing=False)
            for c in unrecognized_attributes
        ]
        unrecognized_with_recommended = [
            f"{c}%s" % (f" (Recommended column name: {r})" if r else "")
            for c, r in zip(unrecognized_attributes, recommended)
        ]
        unrecognized_with_recommended_str = make_logger_bullet_list(
            sorted(
                unrecognized_with_recommended,
                key=lambda x: str(x).lower(),
            )
        )
        warning_log.append(
            f"The following unrecognized columns were found and will be ignored in table '{class_name}' from file {file}:\n{unrecognized_with_recommended_str}"
        )
    return warning_log


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
                        track_file = f"{file['excel_file']}:{file['sheet']}"
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


def get_excel_file_classes(
    file: Union[str, Path], schema: Union[SchemaView, str, Path] = None
) -> Dict[str, List[Dict[str, str]]]:
    if isinstance(schema, (str, Path)):
        schema = SchemaView(schema)

    def _select_class(name: str, classes: List[str]) -> Optional[str]:
        # Determine which class the sheet named "name" should be assigned to
        name = name.strip()
        matches = [c for c in classes if name.endswith(c)]
        if len(matches) == 0:
            return None
        return matches[np.argmax(matches)]

    # Load all sheet names from Excel file
    with pd.ExcelFile(file) as xl:
        sheet_names = list(xl.sheet_names)

    if schema is None:
        all_classes = sheet_names
    else:
        all_classes = all_classes_without_tree_root(schema)
    # Map the sheet names to class names
    sheet_to_class = {
        sheet_name: _select_class(sheet_name, all_classes) for sheet_name in sheet_names
    }
    # Remove any sheet that maps to no class
    sheet_to_class = {s: c for s, c in sheet_to_class.items() if c is not None}

    # Create the results dictionary
    results = {}
    for sheet_name, class_name in sheet_to_class.items():
        if class_name not in results:
            results[class_name] = []
        results[class_name].append({"excel_file": file, "sheet": sheet_name})

    return results


def strip_whitespace(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from all strings in the DataFrame."""
    return df.map(lambda x: x.strip() if isinstance(x, str) else x)


def clear_dirs(
    dirs: Union[Union[str, Path], List[Union[str, Path]]],
    extensions: Union[str, List[str]] = [".tsv", ".csv", ".yaml", ".yml"],
):
    """Remove all TSV, CSV, and YAML files in all the specified directories.

    Args:
        dirs (Union[Union[str, Path], List[Union[str, Path]]]): One or more directories to clean.
        extensions (Union[str, List[str]]): One or more extensions. All files with these
            extensions found in the directories are deleted. These are case-insensitive and
            should be prefixed by a dot.
            (Defaults to [".tsv", ".csv", ".yaml", ".yml"])
    """
    if isinstance(extensions, str):
        extensions = [extensions]
    extensions = [e.lower() for e in extensions]
    if isinstance(dirs, (str, Path)):
        dirs = [dirs]
    for d in dirs:
        logger.debug(f"Clearing directory {d}")
        if os.path.isdir(d):
            for f in os.listdir(d):
                file = Path(d) / f
                if os.path.splitext(file)[1].lower() in extensions:
                    os.remove(file)


def choose_ignore_case_value(
    val: str,
    allowable_values: List[str],
    lowercase_allowable_values: Optional[List[str]] = None,
    return_same_if_missing: Optional[bool] = True,
) -> str:
    """Convert a value to match the capitalization of the same value in allowable_values.

    Args:
        val (str): The value to change the capitalization of.
        allowable_values (List[str]): A list of all allowable values that val may take on. If val matches
            any of these values (ignoring case), then we use the matching value in allowable_values.
        lowercase_allowable_values (Optional[List[str]], optional): All values in allowable_values but in
            lowercase. This is optional, if not specified then we will calculate this ourselves. Specifying
            this is simply to improve performance, so if this function is called many times we can calculate
            lowercase_allowable_values once outside of this function then pass it in for each call.
            Defaults to None.
        return_same_if_missing (Optional[bool], optional): If True and val is not found in
            allowable_values (ignoring case)/lowercase_allowable_values then val is returned unchanged. If
            False and val is not found the None is returned. Defaults to True.

    Returns:
        str: The value with the correct capitalization. If a match is not found in allowable_values then
            the value is returned unchanged.
    """
    if not isinstance(val, str):
        return val

    # Calculate lowercase_allowable_values if required
    if lowercase_allowable_values is None:
        lowercase_allowable_values = [v.lower() for v in allowable_values]

    # Find the match in allowable_values and return it
    lower_val = val.lower()
    if lower_val in lowercase_allowable_values:
        return allowable_values[lowercase_allowable_values.index(lower_val)]
    if return_same_if_missing:
        return val

    return None


def get_class_name_from_file_name(
    file_name: Union[str, Path], schema: Optional[SchemaView] = None
) -> str:
    """Get the LinkML class name based on a data file name. Data files are named as "class_name[...].ext".

    Args:
        file_name (Union[str, Path]): The file name to extract the class name from.
        schema (Optional[SchemaView], optional): If set, then we correct the capitalization of the class name
            based on the classes found in this schema. Defaults to None.

    Returns:
        str: The class name for the data file.
    """
    base_name = os.path.splitext(os.path.basename(file_name))[0]
    class_name = base_name.split("[")[0].split("(")[0]
    if schema is not None:
        class_name = choose_ignore_case_value(
            class_name, all_classes_without_tree_root(schema)
        )
    return class_name


def parse_df_values(df: pd.DataFrame, inline: bool = True) -> pd.DataFrame:
    """Try to parse and convert all values in the DataFrame as numbers (floats or ints).

    This is useful if we want to convert strings to numbers.

    Args:
        df (pd.DataFrame): The DataFrame to parse.
        inline (bool, optional): If True then modify the DataFrame inline. If False then
            the orginal DataFrame is left unchanged and a parsed copy is returned. Defaults to True.

    Returns:
        pd.DataFrame: The input DataFrame modified to have string values converted to integers or
            floats where possible. If inline is True then the input DataFrame is also modified,
            otherwise it is left unchanged and a copy is returned.
    """
    if not inline:
        df = df.copy()
    for col in df.columns:
        df[col] = df[col].map(parse_numeric)
    return df


def parse_numeric(value: str) -> Any:
    """Try to parse a string as a numeric (int or float).

    Args:
        value (str): The string value to convert to an int or float. If it can be converted to
            an int (ie. a number with no decimal point) then the int is returned. If not then
            if it can be converted to a float then the float is returned. Otherwise the value
            is returned unchanged.

    Returns:
        Any: The numeric value of the string. Either an int or float, or if it can't be converted
            to numeric then value is returned unchanged.
    """
    if not isinstance(value, str) or not re.search(r"[0-9]", value):
        return value
    # In newer versions of Python, underscores are allowed in numbers (eg. ints and floats) and
    # are ignored when converting from string to int/float. We want to avoid this new behavior
    # and treat any string with an underscore as a string (not a number) (eg. "123_456" is
    # treated as a string, not the number 123456).
    if "_" in value:
        return value

    # We make the conversion fairly strict. So for example the string "09021" is treated as a string,
    # not an integer. The numeric version of the value must match the string version of the value exactly.
    try:
        int_v = int(value)
        if str(int_v) == value:
            return int_v
    except (TypeError, ValueError):
        pass
    try:
        float_v = float(value)
        if str(float_v) == value:
            return float(value)
    except (TypeError, ValueError, OverflowError):
        return value


def select_func_kwargs(func: Callable, kwargs: Dict[str, Any]) -> Dict[str, Any]:
    """Only select the keyword arguments in the dictionary that are acceptable arguments
    for the function.

    Args:
        func (Callable): The function to get the keyword arguments for.
        kwargs (Dict[str, Any]): The keyword arguments to select from.

    Returns:
        Dict[str, Any]: A dictionary which is a copy of kwargs where only the keys that
            exist as arguments to the function func are present.
    """
    args, _, _, _, kwonlyargs, *_ = inspect.getfullargspec(func)
    all_args = list(dict.fromkeys(list(args) + list(kwonlyargs)))
    existing_keywords = [k for k in all_args if k in kwargs.keys()]
    kwargs = {k: kwargs[k] for k in existing_keywords}
    return kwargs


def get_unique_output_file(file: Union[str, Path]) -> Path:
    """Get an output file name, in the same directory as the specified file and with a similar file name,
    that does not already exist on disk.

    If a file named file already exists, then the returned file name will be of the form file[nnn].ext, where nnn
    is a number that makes the file name unique (ie. it doesn't exist on disk).

    Args:
        file (Union[str, Path]): The full path and filename to base the returned output file on.

    Returns:
        Path: A full path and filename, in the same directory as file, but with a filename that is guaranteed to not
            exist on disk.
    """
    idx = 0
    orig_file = file
    while os.path.exists(file):
        file = f"%s[{idx:03d}]%s" % os.path.splitext(orig_file)
        idx += 1
    return Path(file)


def merge_dicts_of_lists(
    dicts: List[Dict[Any, List]],
) -> Dict[Any, List[Any]]:
    """Combine multiple Dictionaries where the values are lists. When multiple dictionaries
    have the same keys, their lists are combined.

    Args:
        dicts (List[Dict[Any, List]]): List of all dictionaries to merge. If multiple dictionaries
            have the same key, then the lists for those keys are combined to include all values.

    Returns:
        Dict[Any, List[Any]]: Dictionary where the keys are the keys found in the source dicitionaries
            and the values are lists containing all values found in the source dictionary.
    """
    d = {}
    for cur_dict in dicts:
        if cur_dict is None:
            continue
        for k, v in cur_dict.items():
            if k not in d:
                d[k] = []
            d[k].extend(v)
    return d
