"""
General utility functions.
"""

import sys
import os
from pathlib import Path
import pandas as pd
import yaml
import inspect
from typing import Union, List, Optional, Any, Dict, Callable
import logging
import re

from linkml_runtime import SchemaView

EMPTY_PERMISSIBLE_VALUE = "<empty>"

# Name of the tree root Container class that contains all the tables in a LinkML schema
TREE_ROOT_CLASS_NAME = "Container"

RECOGNIZED_EXTENSIONS = [".tsv", ".txt", ".csv", ".yaml", ".yml"]

# LOGGER_FORMAT = "%(levelname)s %(asctime)s %(filename)s:%(lineno)d: %(message)s"
LOGGER_FORMAT = "%(message)s"
LOGGER_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def get_logger(name: str, level: Optional[str] = logging.INFO) -> logging.Logger:
    """Get the logger with the specified name, setting is configuration as well as output format.
    The name can be any arbitrary string. For example:

        logger = get_logger(__name__)

    Args:
        name (str): The name to give to the logger. This can be any arbitrary string and is
            typically the name of the caller.
        level (Optional[str], optional): The logging level of the logger. Defaults to logging.INFO.

    Returns:
        logging.Logger: The logging object.
    """
    handlers = [logging.StreamHandler(sys.stdout)]
    logging.basicConfig(
        handlers=handlers,
        format=LOGGER_FORMAT,
        level=level,
        datefmt=LOGGER_DATE_FORMAT,
    )

    logger = logging.getLogger(name)
    if level:
        logger.setLevel(level)
    return logger


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
    else:
        raise ValueError(f"Unrecognized extension for file {file}")
    return df


def strip_whitespace(df: pd.DataFrame) -> pd.DataFrame:
    """Strip whitespace from all strings in the DataFrame."""
    return df.map(lambda x: x.strip() if isinstance(x, str) else x)


def clear_dirs(
    dirs: Union[Union[str, Path], List[Union[str, Path]]],
    extensions: Union[str, List[str]] = [".tsv", ".csv", ".yaml"],
):
    """Remove all TSV, CSV, and YAML files in all the specified directories.

    Args:
        dirs (Union[Union[str, Path], List[Union[str, Path]]]): One or more directories to clean.
        extensions (Union[str, List[str]]): One or more extensions. All files with these
            extensions found in the directories are deleted. These are case-insensitive and
            should be prefixed by a dot.
            (Defaults to [".tsv", ".csv", ".yaml"])
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
            class_name, list(schema.all_classes().keys())
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
