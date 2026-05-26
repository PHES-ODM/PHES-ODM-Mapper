"""
General utility functions.
"""

import os
from pathlib import Path
import pandas as pd
import yaml
import json
import inspect
from typing import Union, List, Optional, Any, Dict, Callable
import re

from odm_map.utils.logger import get_logger
from odm_map.utils.clean_exit_error import CleanExitError

EMPTY_PERMISSIBLE_VALUE = "<empty>"

# Name of the tree root Container class that contains all the tables in a LinkML schema
TREE_ROOT_CLASS_NAME = "Container"

RECOGNIZED_EXTENSIONS = [".tsv", ".txt", ".csv", ".yaml", ".yml"]

# For Excel files, instead of specifying a path to the file, we create a dictionary where EXCEL_FILE_KEY corresponds
# to the actual Excel file and EXCEL_SHEET_KEY corresponds to the sheet to load from the Excel file. For non-Excel
# files (eg. csv, tsv, txt, yaml, yml) we just use the file name as a regular string (rather than a dictionary)
EXCEL_FILE_KEY = "excel_file"
EXCEL_SHEET_KEY = "sheet"

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
    elif ext in [".xlsx"]:
        df.to_excel(output_file, **kwargs)
    elif ext in [".yaml", ".yml"]:
        with open(output_file, "w") as f:
            data = {c: list(df[c]) for c in df.columns}
            yaml.dump(data, f)
    else:
        raise ValueError(f"Extension not supported in save_data_frame: {output_file}")


def read_data_frame(
    file: Union[str, Dict[str, str]], **kwargs
) -> Union[pd.DataFrame, Dict[str, pd.DataFrame]]:
    """Read a Pandas DataFrom from disk.

    Args:
        file (Union[str, Dict[str, str]]): The file to read. Supports loading files with any of the extensions in
            RECOGNIZED_EXTENSIONS. If an Excel file then the first sheet is loaded if "sheet_name" is not found in
            kwargs. If "sheet_name" is found in kwargs then it is passed to pd.read_excel to that sheet (or
            multiple sheets). Alternatively, if file is a Dictionary, then the sheet name can be specified there,
            as shown below:
                {
                    EXCEL_FILE_KEY: "myfile.xlsx",
                    EXCEL_SHEET_KEY: "mysheet",
                }
        **kwargs: Additional key-word arguments passed to the reading function called to load the
            DataFrame (eg. the additional arguments to pd.read_csv or pd.read_excel).

    Returns:
        Union[pd.DataFrame, Dict[str, pd.DataFrame]]: The DataFrame loaded from the file, or if multiple DataFrames
            were loaded (from sheet_name or EXCEL_SHEET_KEY being a list of sheet names) then a dictionary where the
            keys are the sheet name and the values are the DataFrame for that sheet.
    """
    if isinstance(file, Dict):
        sheet_name = file[EXCEL_SHEET_KEY]
        file = file[EXCEL_FILE_KEY]
    else:
        sheet_name = 0
        if kwargs is not None and "sheet_name" in kwargs:
            sheet_name = kwargs.get("sheet_name")
            del kwargs["sheet_name"]

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
        pass
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


def save_data_frames_for_classes(
    data_frames: Dict[str, List[pd.DataFrame]],
    output_dir: Union[str, Path],
    file_name_format="{class_name}.csv",
    save_to_data_files: Optional[Dict[str, List[Union[str, Path]]]] = None,
) -> Dict[str, List[Path]]:
    """Save the DataFrames to disk, combining the DataFrames for each class into one
    DataFrame per class.

    Args:
        data_frames (Dict[str, List[pd.DataFrame]]): The dictionary of DataFrames to save to disk.
            The keys are the class names and the values are lists of DataFrames for the class. The lists
            are merged into a single DataFrame then saved to disk.
        output_dir (Union[str, Path]): The directory to save the data to.
        file_name_format (str, optional): The file name to use for saving to disk. Can include the
            {class_name} string interpolation value to include the class name in the file name. Defaults
            to "{class_name}.csv".
        save_to_data_files (Optional[Dict[str, List[Union[str, Path]]]], optional): If set, then this
            dictionary receives the paths of the saved files. The keys are the class names and the values
            are lists of file names. This function will only add one file name per class to the
            list. Defaults to None.

    Returns:
        Dict[str, List[Path]]: The list of files saved to disk. The keys are the class names and
            the values are lists of paths to saved files. If save_to_data_files was set then the files
            are added to save_to_data_files and returned.
    """
    if not save_to_data_files:
        save_to_data_files = {}
    else:
        # Make sure all existing data files are Path objects (instead of str)
        for class_name, files in save_to_data_files.items():
            for idx in range(len(files)):
                files[idx] = Path(files[idx])

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        for class_name, all_df in data_frames.items():
            # Concatenate all DataFrames so we save to a single output file per class
            df = pd.concat(all_df, ignore_index=True, axis=0)
            output_file = os.path.join(
                output_dir, file_name_format.format(class_name=class_name)
            )
            save_data_frame(df, output_file, index=False)
            if class_name not in save_to_data_files:
                save_to_data_files[class_name] = []
            save_to_data_files[class_name].append(Path(output_file))
    return save_to_data_files


def load_data_frames_for_classes(
    data_files: Optional[Dict[str, List[Union[str, Path, Dict]]]],
    save_to_data_frames: Optional[Dict[str, List[pd.DataFrame]]] = None,
    max_rows: Optional[int] = None,
) -> Dict[str, List[pd.DataFrame]]:
    """Load lists of data files associated with various classes.

    The returned dictionary contains the class names (the keys of the dictionary) and the list of DataFrames for that class
    (the values of the dictionary).

    Args:
        data_files (Optional[Dict[str, List[Union[str, Path, Dict]]]]): List of data files to load. The keys are the class
            names for the data files, and the values are lists of files to load for that class.
        save_to_data_frames (Optional[Dict[str, List[pd.DataFrame]]], optional): If set, then add the loaded DataFrames to
            this dictionary, where the keys are the class names and the values are lists of DataFrames for the class. Each
            DataFrame loaded from data_files gets appended to the end of the list for the class. Defaults to None.
        max_rows (Optional[int], optional): Maximum number of rows to load from each data file. If 0 or None then all rows
            are loaded. Defaults to None.

    Returns:
        Dict[str, List[pd.DataFrame]]: Dictionary of loaded DataFrames, where the keys are the class names and the values
            are the DataFrames for that class. If save_to_data_frames was specified, then save_to_data_frames gets modified
            by appending the newly loaded DataFrames from data_files, and save_to_data_frames is also returned.
    """
    if save_to_data_frames is None:
        save_to_data_frames = {}
    if not data_files:
        return save_to_data_frames

    for class_name, class_files in data_files.items():
        if class_name not in save_to_data_frames:
            save_to_data_frames[class_name] = []
        for class_file in class_files:
            df = read_data_frame(
                class_file,
                nrows=max_rows if max_rows and max_rows > 0 else None,
                keep_default_na=False,
                na_values=None,
            )
            save_to_data_frames[class_name].append(df)

    return save_to_data_frames


def make_multivalued(v: Any) -> List[Any]:
    """Make a string (typically from a DataFrame) multivalued. This means converting it to a list of values.

    We try to load the value as as JSON or YAML. If that doesn't work we split on the character "," or ";".

    Args:
        v (Any): The value to convert to multivalued.

    Returns:
        List[Any]: The multivalued version of v. If v is a single value then it will be an array of size 1.
    """
    if isinstance(v, str):
        try:
            vs = json.loads(v)
            if isinstance(vs, list):
                return vs
        except Exception:
            pass
        try:
            vs = yaml.safe_load(v)
            if isinstance(vs, list):
                return vs
        except Exception:
            pass

        # @TODO: This doesn't properly deal with commas and semi-colons nested within
        # quotes, which we would typically not want to split on. This is how LinkML does it,
        # but it may not be good in all situations.
        # Deal with comma or semi-colon separated multi-values. eg. "a,b,c" or "a;b;c" map
        # to the array ['a', 'b', 'c']
        for delimiter in ",;":
            if delimiter in v:
                vs = v.split(delimiter)
                vs = [v.strip() if isinstance(v, str) else v for v in vs]
                return vs
    elif isinstance(v, (list, tuple)):
        return list(v)

    return [v]
