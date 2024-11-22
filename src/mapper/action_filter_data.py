import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from typing import Dict, List, Union
from pathlib import Path
import pandas as pd
from datetime import datetime

from filter.filter_data import DataFilter
from utils.general_utils import get_logger

logger = get_logger(__name__)


def action_filter_data(
    data_frames: Dict[str, List[pd.DataFrame]],
    filter_config_file: Union[str, Path],
) -> Dict[str, List[pd.DataFrame]]:
    """Filter DataFrames according to a filter configuration file.

    Args:
        data_frames (Dict[str, List[pd.DataFrame]]): Dictionary of DataFrames to filter, where the
            keys are the class names and the values are lists of DataFrames belonging to the class.
            All DataFrames from the same class are merged then filtered.
        filter_config_file (Union[str, Path]): The filter configuration file to use (a CSV file)

    Returns:
        Dict[str, List[pd.DataFrame]]: The filtered DataFrames. Keys are the class names and values
            are lists of filtered DataFrames for that class.
    """
    logger.debug("Filtering all data...")
    filter_tic = datetime.now()
    data_filter = DataFilter(filter_config_file)

    # Merge data
    merged_data = {}
    for class_name, dfs in data_frames.items():
        df = pd.concat(dfs, ignore_index=True, axis=0)
        merged_data[class_name] = df

    # Filter data
    filtered_data, _ = data_filter.run_filter(data=merged_data)
    filtered_data = {k: [v] for k, v in filtered_data.items()}

    logger.debug(f"Total time for filtering: {datetime.now() - filter_tic}")

    return filtered_data
