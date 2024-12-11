"""
Command-line interface utilities.
"""

import os
import pandas as pd

from typing import Dict, List, Union, Optional
from pathlib import Path

from linkml_runtime import SchemaView

from odm_map.utils.general_utils import (
    merge_dicts_of_lists,
    EXCEL_FILE_KEY,
    EXCEL_SHEET_KEY,
)
from odm_map.utils.schema_utils import (
    find_class,
    get_class,
    all_classes_without_tree_root,
)
from odm_map.utils.logger import get_logger
from odm_map.utils.clean_exit_error import CleanExitError

# When explicitly specifying the class name that a file belongs to (when using the CLI),
# the file path is prefixed by the class name, then CLASS_PREFIX_SEPARATOR. For example,
# if CLASS_PREFIX_SEPARATOR is ":", then we can use "WWMeasure:path/to/data.csv" to
# explicitly specify that data.csv belongs to the class WWMeasure.
CLASS_PREFIX_SEPARATOR = ":"

logger = get_logger(__name__)


def get_input_data_files_from_dir(
    directory: Union[str, Path],
    schema: Optional[Union[SchemaView, str, Path]] = None,
    exception_on_unknown: bool = False,
) -> Dict[str, List[Path]]:
    """Get all data files (csv, txt, tsv) in the directory and the class that the data file
    is for. The class is determined by the file name, without extension and with anything after
    the first square bracket removed. For example, "measures[2024-09-25].csv" would be a data
    file for the "measures" class. The class might not be a valid class name, and should
    be checked by the caller.

    Args:
        directory (Union[str, Path]): The directory to get the files from.
        schema (Optional[Union[SchemaView, str, Path]], optional): The schema that the files are for.
            We will only retrieve the files that belong to the classes in the schema (ie. have the same
            file name as a recognized class in the schema, ignoring anything after the first open square
            or round bracket). For Excel files, we will retrieve the sheets that belong to the classes.
            If None then all files and sheets are retrieved, regardless of class. Default to None.
        exception_on_unknown (bool, optional): If True then raise an exception if a file is found that
            does not belong to a valid class name in the schema. If False the do not raise an
            exception and instead just ignore the file.

    Returns:
        Dict[str, List[Path]]: Dictionary where the keys are class names (they might not be valid
            class names, so should be checked by callers) and the values are lists of files representing
            data for those classes.
    """
    if isinstance(schema, (str, Path)):
        schema = SchemaView(schema)

    directory = Path(directory)
    d = {}
    if not directory.is_dir():
        raise CleanExitError(f"Specified path is not a directory: {directory}")
    for f in os.listdir(directory):
        f = directory / f
        info = get_file_info(f, schema=schema, exception_on_error=False)
        if info is not None:
            d = merge_dicts_of_lists([d, info])
        elif exception_on_unknown:
            raise CleanExitError(f"Could not determine table for file: {f}")

    # Sort by class name
    d = dict(sorted(d.items()))
    return d


def get_excel_file_info(
    file: Union[str, Path], schema: Union[SchemaView, str, Path] = None
) -> Dict[str, List[Dict[str, str]]]:
    """Get all the information for the sheets in the  specified Excel file. The information
    consists of the class name that the sheet belongs to.

    Args:
        file (Union[str, Path]): The Excel file to get the information for.
        schema (Union[SchemaView, str, Path], optional): The schema that the Excel file sheets
            belong to. This is used to identify recognized classes. If a sheet name contains
            a recognized class then it is assumed to belong to that class. The longest matching
            sheet name is used. Sheets that do not belong to a class are ignored and not
            includeded in the returned information. If None then it is assumed
            that all sheets are named after the class they belong to and that the class is valid.
            Defaults to None.

    Returns:
        Dict[str, List[Dict[str, str]]]: Dictionary of the form { class_name: [info, ...]}
            where each sheet that belongs to a recognized class has it's own info belonging
            to a specific class. The info is of the form
            { EXCEL_FILE_KEY: file, EXCEL_SHEET_KEY: "sheet_name" }
    """
    file = Path(file)

    if isinstance(schema, (str, Path)):
        schema = SchemaView(schema)

    # Load all sheet names from Excel file
    with pd.ExcelFile(file) as xl:
        sheet_names = list(xl.sheet_names)

    # Map the sheet names to class names
    sheet_to_class = {
        sheet_name: find_class(sheet_name, schema, ignore_case=True)
        for sheet_name in sheet_names
    }
    # Remove any sheet that maps to no class
    sheet_to_class = {s: c for s, c in sheet_to_class.items() if c is not None}

    # Create the results dictionary
    results = {}
    for sheet_name, class_name in sheet_to_class.items():
        if class_name not in results:
            results[class_name] = []
        results[class_name].append({EXCEL_FILE_KEY: file, EXCEL_SHEET_KEY: sheet_name})

    return results


def get_file_info(
    file: Path,
    schema: Optional[SchemaView],
    parse_class_prefix: bool = False,
    exception_on_error: bool = True,
) -> Optional[Dict]:
    """Get the information for the specified file. The information is in the format
    { class_name: [info, ...] } where info is either the file path or a Dictionary of the
    form { EXCEL_FILE_KEY: file, EXCEL_SHEET_KEY: "sheet" }. For Excel files there
    can be multiple info fields (one for each tab that belongs to a recognized class)

    Args:
        file (Path): The file to get the information for.
        schema (Optional[SchemaView]): The SchemaView that the file belongs to. If set then
            the class name for the file (based on the file name or the Excel
            sheet names) will be verified. If it is not a recognized class then None
            is returned (or for Excel files the sheet is ignored).
        parse_class_prefix (bool, optional): If True then if the file is a CSV, TSV, or
            TXT file then try to parse the explicit class name from the passed-in file
            name. The explicit class name is prefixed to the file path, followed by
            CLASS_PREFIX_SEPARATOR (eg. "WWMeasure:path/to/data.csv" has the class
            prefix "WWMeasure", which is used to explicitly specify what table the file
            belongs to). Defaults to False.
        exception_on_error (bool, optional): If True and an error occurs then raise an
            exception. An error occurs if the file does not exist, or does not belong
            to a recognized class, or the explicit class prefix is not a valid class
            name. For Excel files, sheets that do not belong to a recognized class are
            ignored (ie. it is not an error). If False then return None on error without
            raising an exception. Defaults to True.

    Returns:
        Optional[Dict]: A dictionary of the file information. The information is in the
            format { class_name: [info, ...] } where info is either the file path or a
            Dictionary of the form { EXCEL_FILE_KEY: file, EXCEL_SHEET_KEY: "sheet" }.
            For Excel files there can be multiple info fields (one for each tab that
            belongs to a recognized class)
    """

    def _return_error(msg: str, file: str) -> None:
        if exception_on_error:
            msg = f"{msg}: {file}"
            raise CleanExitError(msg)
        else:
            if not msg.endswith("."):
                msg = f"{msg}."
            msg = f"{msg} Ignoring file: {file}"
            logger.warning(msg)
        return None

    file = str(file)
    ext = os.path.splitext(file)[1].lower()
    if ext in [".tsv", ".txt", ".csv"]:
        if parse_class_prefix and CLASS_PREFIX_SEPARATOR in file:
            # Format is class_name:path/file.ext
            orig_class_name, orig_file = file.split(":", maxsplit=1)
            if not os.path.isfile(orig_file):
                return _return_error("File does not exist", orig_file)

            if schema is not None:
                # Make sure the explicit class exists
                class_name = get_class(orig_class_name, schema, ignore_case=False)
            else:
                # No schema provided, so there's no way to know if the class is valid or not.
                # Assume it's valid
                class_name = orig_class_name
            if not class_name:
                return _return_error(f"Unrecognized table '{orig_class_name}'", file)

            return {class_name: [orig_file]}
        else:
            if not os.path.isfile(file):
                return _return_error("File does not exist", file)

            # No explicit class specified in the file, so try to determine the class based on
            # the file name.
            class_name = find_class(
                os.path.splitext(os.path.basename(file))[0], schema, ignore_case=True
            )
            if class_name is None:
                return _return_error(
                    "File name must match a table name, but none were found", file
                )

            return {class_name: [file]}
    elif ext in [".xlsx"]:
        if not os.path.isfile(file):
            return _return_error("File does not exist", file)
        try:
            info = get_excel_file_info(file, schema=schema)
        except Exception:
            return _return_error("Could not load Excel file", file)
        if not info:
            all_classes = all_classes_without_tree_root(schema)
            all_classes = ", ".join(all_classes)
            return _return_error(
                f"Excel file sheet names must match table names, but none were found. Allowable classes are: {all_classes}",
                file,
            )
        return info
    else:
        return _return_error(f"Unrecognized extension '{ext}'", file)


def get_input_data_files(
    inputs: List[str],
    schema: Optional[Union[SchemaView, str, Path]] = None,
) -> Dict[str, List[Union[Path, Dict]]]:
    """Get all the files in the specified inputs, which consist of a list of either files and/or
    directories. For directories we extract all the files in the dictionary and add them to the
    returned value.

    Args:
        inputs (List[str]): List of files and/or directories. For files they can optionally be
            preceded by the class name that the file belongs to (eg. "WWMeasure:path/to/data.csv").
            If the class is not explicitly specified then the file name is searched for the class
            name. For Excel files the sheets are added to the returned value, where the info
            is of the form { class_name: [{EXCEL_FILE_KEY: file, EXCEL_SHEET_KEY: "sheet_name"}] }.
            The sheet names are used to determine the class name (if no class name is identified
            then the sheet is ignored).
        schema (Optional[Union[SchemaView, str, Path]], optional): The schema that the inputs belong
            to. This schema lists all the recognized class names. Defaults to None.

    Returns:
        Dict[str, List[Union[Path, Dict]]]: Dictionary for all the information for the inputs.
            The keys are the class names, the values are lists of file paths and/or file dictionaries.
            File dictionaries are used to specify the file name and sheet name within an Excel file,
            in the format {EXCEL_FILE_KEY: file, EXCEL_SHEET_KEY: "sheet_name"}.
    """
    if schema is not None and not isinstance(schema, SchemaView):
        schema = SchemaView(schema)

    all_files = {}
    for inp in inputs:
        inp = Path(inp)
        if inp.is_dir():
            # Input is a directory, get all recognized files in it as an info
            # dictionary {class_name_a: [files, ...], class_name_b: [files, ...], ...}
            info = get_input_data_files_from_dir(
                inp, schema=schema, exception_on_unknown=False
            )
            if info is not None:
                all_files = merge_dicts_of_lists([all_files, info])
        elif inp.is_file():
            # Input is a file, so get the file info dictionary {class_name: [file]}
            info = get_file_info(inp, schema=schema, parse_class_prefix=True)
            if info is not None:
                all_files = merge_dicts_of_lists([all_files, info])
        else:
            raise CleanExitError(f"Input does not exist: {inp}")
    return all_files
