"""
Command-line interface utilities.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from linkml_runtime import SchemaView

from typing import Dict, List, Union, Optional
from pathlib import Path
from utils.general_utils import (
    get_class_name_from_file_name,
    merge_dicts_of_lists,
    get_excel_file_classes,
)
from utils.clean_exit_error import CleanExitError


def parse_input_data_files_cli_args(cli_args: List[str]) -> Dict[str, List[Path]]:
    """Parse CLI input arguments to specify input data files and the class they belong to.

    Args:
        cli_args (List[str]): List of arguments. Arguments occur in pairs, with first argument in the pair
            being the class name for the file and the second being the data file for the class. Multiple
            files for the same class can be specified, but each file must be preceded by the class name.
            For example:

                cli_args = ["measures", "measures_data.csv", "measures", "measures2.csv", "samples", "samples_data.csv" ]

            The above will result in a return value of:

                {
                    "measures": [ "measures_data.csv", "measures2.csv" ],
                    "samples": [ "samples_data.csv" ]
                }

    Returns:
        Dict[str, List[Path]]: Dictionary where the keys are class names (they might not be valid
            class names, so should be checked by callers) and the values are lists of files representing
            data for those classes.
    """
    d = {}
    for idx in range(len(cli_args) // 2):
        class_name, file = cli_args[idx * 2 : idx * 2 + 2]
        if class_name not in d:
            d[class_name] = []
        d[class_name].append(Path(file))
    return d


def get_input_data_files_from_dir(
    dir: Union[str, Path], schema: Optional[Union[SchemaView, str, Path]] = None
) -> Dict[str, List[Path]]:
    """Get all data files (csv, txt, tsv) in the directory and the class that the data file
    is for. The class is determined by the file name, without extension and with anything after
    the first square bracket removed. For example, "measures[2024-09-25].csv" would be a data
    file for the "measures" class. The class might not be a valid class name, and should
    be checked by the caller.

    Args:
        dir (Union[str, Path]): The directory to get the files from.
        schema (Optional[Union[SchemaView, str, Path]], optional): The schema that the files are for.
            We will only retrieve the files that belong to the classes in the schema (ie. have the same
            file name as a recognized class in the schema, ignoring anything after the first open square
            or round bracket). For Excel files, we will retrieve the sheets that belong to the classes.
            If None then all files and sheets are retrieved, regardless of class. Default to None.

    Returns:
        Dict[str, List[Path]]: Dictionary where the keys are class names (they might not be valid
            class names, so should be checked by callers) and the values are lists of files representing
            data for those classes.
    """
    if isinstance(schema, (str, Path)):
        schema = SchemaView(schema)

    dir = Path(dir)
    d = {}
    if not dir.is_dir():
        raise CleanExitError(f"Specified path is not a directory: {dir}")
    for f in os.listdir(dir):
        ext = os.path.splitext(f)[1].lower()
        if ext in [".tsv", ".txt", ".csv"]:
            class_name = get_class_name_from_file_name(f)
            if not class_name:
                continue
            if class_name not in d:
                d[class_name] = []
            d[class_name].append(dir / f)
        elif ext in [".xlsx"]:
            excel_file = get_excel_file_classes(dir / f, schema=schema)
            for class_name, files in excel_file.items():
                for sub_file in files:
                    if class_name not in d:
                        d[class_name] = []
                    d[class_name].append(sub_file)

    # Sort by class name
    d = dict(sorted(d.items()))
    return d


def get_input_data_files(
    cli_args: Optional[List[str]],
    dir: Optional[Union[str, Path]],
    schema: Optional[Union[SchemaView, str, Path]] = None,
) -> Dict[str, List[Union[str, Path, Dict[str, str]]]]:
    """Get all input data files from both the command-line arguments and a directory. The full list
    of files is merged.

    Args:
        cli_args (Optional[List[str]]): The CLI arguments to parse to extract class names and files from.
            This parameter is passed to  parse_input_data_files_cli_args to get the list of files.
        dir (Optional[Union[str, Path]]): The directory to retrieve class names and input data files from.
            This parameter is passed to get_input_data_files_from_dir to get the list of files.
        schema (Optional[Union[SchemaView, str, Path]], optional): The schema that the files are for. Only
            files from recognized classes are retrieved. If None then all files are retrieved, regardless of class.
            Defaults to None.
    Returns:
        Dict[str, List[Path]]: Dictionary where the keys are class names (they might not be valid
            class names, so should be checked by callers) and the values are lists of files representing
            data for those classes. It is the combination of all files retrieved from cli_args and
            dir.
    """
    d = {}
    if cli_args is not None:
        cli_d = parse_input_data_files_cli_args(cli_args)
        d = merge_dicts_of_lists([d, cli_d])
    if dir is not None:
        dir_d = get_input_data_files_from_dir(dir, schema=schema)
        d = merge_dicts_of_lists([d, dir_d])
    return d
