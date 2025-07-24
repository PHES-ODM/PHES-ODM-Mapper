from typing import Dict, List, Union
from pathlib import Path
import pandas as pd
from datetime import datetime

from odm_map.filter.filter_data import DataFilter
from odm_map.utils.logger import get_logger

logger = get_logger(__name__)


def action_filter_data(
    data_frames: Dict[str, List[pd.DataFrame]],
    filter_config_file: Union[str, Path],
    debug_mode: bool,
) -> Dict[str, List[pd.DataFrame]]:
    """Filter DataFrames according to a filter configuration file.

    Args:
        data_frames (Dict[str, List[pd.DataFrame]]): Dictionary of DataFrames to filter, where the
            keys are the class names and the values are lists of DataFrames belonging to the class.
            All DataFrames from the same class are merged then filtered.
        filter_config_file (Union[str, Path]): The filter configuration file to use (a CSV file).
        debug_mode (bool): If True then run the filter in debug mode. In debug mode instead of
            dropping rows, we set the value for the column filter_funcs.DROP_COLUMN to True. There may
            be other differences depending on which filters are applied. See the docstrings for the
            functions in filter_funcs.py for details.

    Returns:
        Dict[str, List[pd.DataFrame]]: The filtered DataFrames. Keys are the class names and values
            are lists of filtered DataFrames for that class.
    """
    logger.debug("Filtering all data...")
    filter_tic = datetime.now()
    data_filter = DataFilter(filter_config_file)

    # Merge data into single DataFrames per class
    merged_data = {}
    for class_name, dfs in data_frames.items():
        df = pd.concat(dfs, ignore_index=True, axis=0)
        merged_data[class_name] = df

    # Filter data
    filtered_data, _ = data_filter.run_filter(data=merged_data, debug_mode=debug_mode)
    filtered_data = {k: [v] for k, v in filtered_data.items()}

    logger.debug(f"Total time for filtering: {datetime.now() - filter_tic}")

    return filtered_data
