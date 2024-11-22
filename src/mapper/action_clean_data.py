from typing import Dict, List, Union
from pathlib import Path
import pandas as pd

from linkml_runtime import SchemaView

from cleaner import DataCleaner


def action_clean_data(
    data_frames: Dict[str, List[pd.DataFrame]],
    schema: Union[SchemaView, str, Path],
) -> Dict[str, List[pd.DataFrame]]:
    """Clean the data in the specified data files and DataFrames.

    Args:
        data_frames (Dict[str, List[pd.DataFrame]]): Dictionary of DataFrames, where the keys are the class names
            and the values are lists of DataFrames for that class to clean.
        schema (Union[SchemaView, str, Path]): The schema that the data belong to. It should contain classes
            for all the classes in data_frames. Cleaning will involve correcting capitalization of enumerations
            and other changes.

    Returns:
        Dict[str, List[pd.DataFrame]]: Dictionary where the keys are the class names and the values are lists
                    of DataFrames that are cleaned.
    """
    cleaner = DataCleaner(schema=schema)
    _, data_frames = cleaner.clean_data(
        data_files=None, data_frames=data_frames, output_dir=None
    )
    return data_frames
