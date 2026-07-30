from pathlib import Path

import pandas as pd

from odm_map.expander import ArrayExpander


def action_expand_data(
    data_frames: dict[str, list[pd.DataFrame]],
    config: str | Path,
) -> dict[str, list[pd.DataFrame]]:
    """Expand the data in the specified data files and DataFrames.

    Args:
        data_frames (dict[str, list[pd.DataFrame]]): Dictionary of DataFrames, where the keys are the class names
            and the values are lists of DataFrames for that class to expand.
        config (str | Path): Path to the configuration file for the expander.

    Returns:
        dict[str, list[pd.DataFrame]]: Dictionary where the keys are the class names and the values are lists
                    of DataFrames that are expanded.
    """
    expander = ArrayExpander(config=config)
    _, data_frames = expander.expand_data(
        data_files=None,
        data_frames=data_frames,
        output_dir=None,
    )
    return data_frames
