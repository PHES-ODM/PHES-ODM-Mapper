from typing import Dict, List, Union
import pandas as pd
from pathlib import Path

from odm_map.id_generator import IDGenerator


def action_generate_ids(
    data_frames: Dict[str, List[pd.DataFrame]],
    id_config_file: Union[str, Path],
    id_code_files: List[Dict],
    multi_bar_progress: bool,
    keep_extra_columns: bool = True,
    keep_tracking_columns: bool = True,
    debug_mode: bool = False,
) -> Dict[str, List[pd.DataFrame]]:
    """Generate IDs in the data.

    Args:
        data_frames (Dict[str, List[pd.DataFrame]]): The data frames to add IDs to.
        id_config_file (Union[str, Path]): ID Generator config file.
        id_code_files (List[Dict]): List of dictionaries specifying the files containing the ID code. The
            dictionaries are of the form {"id_code_file": "file.xlsx", "id_code_sheet": "sheet"}. id_code_file
            can be a CSV, TSV, or XLSX file. If an XLSX file then "id_code_sheet" specifies which sheet in
            the Excel file to use. If "id_code_sheet" is None or missing then the first sheet is used.
        multi_bar_progress (bool): If True, then show a progress bar for each class to generate the IDs
            for at the same time. If False then only show one progress bar at a time. False should be
            used in a Jupyter notebook.
        keep_extra_columns (bool, optional): If True, then keep the extra columns in the final DataFrame. These
            are columns that start with the string extra_and_tracking_slots.EXTRA_SLOT_PREFIX and end with the
            string extra_and_tracking_slots.EXTRA_SLOT_SUFFIX. If False then they are removed. Defaults to True.
        keep_tracking_columns (bool, optional): If True, then keep the tracking columns in the final DataFrame.
            These are columns that specify from which row and file/table each of the output rows was populated
            from. Tracking columns start with the string extra_and_tracking_slots.TRACKING_SLOT_PREFIX and end
            with the string extra_and_tracking_slots.TRACKING_SLOT_SUFFIX. If False then these columns are
            dropped. Defaults to True.
        debug_mode (bool, optional): If True then run in debug mode. With debug mode the final output
            will contain additional columns that were used during runtime, such as the old values of
            all the IDs, hash values, etc. Rows with duplicate primary keys will also not be dropped,
            instead, an additional column will be added where the value is True if that row would be
            dropped in non-debug mode. Defaults to False.

    Returns:
        Dict[str, List[pd.DataFrame]]: Dictionary of DataFrames containing the data with IDs generated. The keys are
            the class names and the values are lists of DataFrames containing the generated data.
    """
    gen = IDGenerator(
        data_files=None,
        data_frames=data_frames,
        config_file=id_config_file,
        id_code_files=id_code_files,
        multi_bar_progress=multi_bar_progress,
    )
    return gen.run_generator(
        keep_extra_columns=keep_extra_columns,
        keep_tracking_columns=keep_tracking_columns,
        keep_debug_columns=debug_mode,
        remove_duplicates=not debug_mode,
    )
