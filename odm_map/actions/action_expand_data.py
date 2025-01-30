from typing import Dict, List, Union
from pathlib import Path
import pandas as pd

from odm_map.expander import ArrayExpander


def action_expand_data(
    data_frames: Dict[str, List[pd.DataFrame]],
    config: Union[str, Path],
) -> Dict[str, List[pd.DataFrame]]:
    """Clean the data in the specified data files and DataFrames.

    Args:
        data_frames (Dict[str, List[pd.DataFrame]]): Dictionary of DataFrames, where the keys are the class names
            and the values are lists of DataFrames for that class to expand.
        config (Union[str, Path]): Path to the configuration file for the expander.

    Returns:
        Dict[str, List[pd.DataFrame]]: Dictionary where the keys are the class names and the values are lists
                    of DataFrames that are expanded.
    """
    expander = ArrayExpander(config=config)
    _, data_frames = expander.expand_data(
        data_files=None,
        data_frames=data_frames,
        output_dir=None,
    )
    return data_frames
