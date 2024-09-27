"""
Command-line interface utilities.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import Dict, List, Union, Optional
from pathlib import Path
from utils.general_utils import get_class_name_from_file_name


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


def get_input_data_files_from_dir(dir: Union[str, Path]) -> Dict[str, List[Path]]:
    """Get all data files (csv, txt, tsv) in the directory and the class that the data file
    is for. The class is determined by the file name, without extension and with anything after
    the first square bracket removed. For example, "measures[2024-09-25].csv" would be a data
    file for the "measures" class. The class might not be a valid class name, and should
    be checked by the caller.

    Args:
        dir (Union[str, Path]): The directory to get the files from.

    Returns:
        Dict[str, List[Path]]: Dictionary where the keys are class names (they might not be valid
            class names, so should be checked by callers) and the values are lists of files representing
            data for those classes.
    """
    dir = Path(dir)
    d = {}
    for f in os.listdir(dir):
        if os.path.splitext(f)[1].lower() in [".tsv", ".txt", ".csv"]:
            class_name = get_class_name_from_file_name(f)
            if not class_name:
                continue
            if class_name not in d:
                d[class_name] = []
            d[class_name].append(dir / f)
    return d


def get_input_data_files(
    cli_args: Optional[List[str]], dir: Optional[Union[str, Path]]
) -> Dict[str, List[Path]]:
    """Get all input data files from both the command-line arguments and a directory. The full list
    of files is merged.

    Args:
        cli_args (Optional[List[str]]): The CLI arguments to parse to extract class names and files from.
            This parameter is passed to  parse_input_data_files_cli_args to get the list of files.
        dir (Optional[Union[str, Path]]): The directory to retrieve class names and input data files from.
            This parameter is passed to get_input_data_files_from_dir to get the list of files.
    Returns:
        Dict[str, List[Path]]: Dictionary where the keys are class names (they might not be valid
            class names, so should be checked by callers) and the values are lists of files representing
            data for those classes. It is the combination of all files retrieved from cli_args and
            dir.
    """
    d = {}
    if cli_args is not None:
        cli_d = parse_input_data_files_cli_args(cli_args)
        d = merge_input_data_files([d, cli_d])
    if dir is not None:
        dir_d = get_input_data_files_from_dir(dir)
        d = merge_input_data_files([d, dir_d])
    return d


def merge_input_data_files(
    data_files: List[Dict[str, List[Path]]],
) -> Dict[str, List[Path]]:
    """Combine multiple input data files dictionaries (created by parse_input_data_files_cli_args
    and/or get_input_data_files_from_dir) into a single dictionary.

    Args:
        data_files (List[Dict[str, List[Path]]]): List of all input data files dictionaries. Each
            dictionary has keys that are class names and values that are lists of files for the
            class. If multiple dictionaries have the same key, then the lists for those keys
            are combined to include all values.

    Returns:
        Dict[str, List[Path]]: Dictionary where the keys are class names (they might not be valid
            class names, so should be checked by callers) and the values are lists of files representing
            data for those classes. The lists of files include all files found in the original
            data_files.
    """
    d = {}
    for cur_data_files in data_files:
        for k, v in cur_data_files.items():
            if k not in d:
                d[k] = []
            d[k].extend(v)
    return d
