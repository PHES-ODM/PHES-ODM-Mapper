import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import Dict, List, Union
import pandas as pd
from pathlib import Path

from id_generator import IDGenerator


def action_generate_ids(
    data_frames: Dict[str, List[pd.DataFrame]],
    id_config_file: Union[str, Path],
    id_code_file: Union[str, Path],
    id_code_sheet: Union[str, Path],
    multi_bar_progress: bool,
    debug_mode: bool = False,
) -> Dict[str, List[pd.DataFrame]]:
    """Generate IDs in the data.

    Args:
        data_frames (Dict[str, List[pd.DataFrame]]): The data frames to add IDs to.
        id_config_file (Union[str, Path]): ID Generator config file.
        id_code_file (Union[str, Path]): File containing the code for generating IDs (csv, tsv, xlsx).
        id_code_sheet (Union[str, Path]): If id_code_file is an Excel file, then this is the sheet
            to use in the code file.
        multi_bar_progress (bool): If True, then show a progress bar for each class to generate the IDs
            for at the same time. If False then only show one progress bar at a time. False should be
            used in a Jupyter notebook.
        debug_mode (bool, optional): If True then run in debug mode. With debug mode the final output
            will contain additional columns that were used during runtime, such as the old values of
            all the IDs, the tracking columns (source file and row), etc. Rows with duplicate primary
            keys will also not be dropped, instead, an additional column will be added where the value
            is True if that row would be dropped in non-debug mode. Defaults to False.

    Returns:
        Dict[str, List[pd.DataFrame]]: Dictionary of DataFrames containing the data with IDs generated. The keys are
            the class names and the values are lists of DataFrames containing the generated data.
    """
    gen = IDGenerator(
        data_files=None,
        data_frames=data_frames,
        config_file=id_config_file,
        id_code_file=id_code_file,
        id_code_sheet=id_code_sheet,
        multi_bar_progress=multi_bar_progress,
    )
    return gen.run_generator(
        orig_columns_only=not debug_mode, remove_duplicates=not debug_mode
    )
