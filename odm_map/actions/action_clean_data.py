from pathlib import Path
from typing import Any

import pandas as pd
from linkml_runtime import SchemaView

from odm_map.cleaner import DataCleaner


def action_clean_data(
    data_frames: dict[str, list[pd.DataFrame]],
    schema: SchemaView | str | Path,
    log_file: str | Path,
    clean_operations: list[dict[str, Any]],
) -> dict[str, list[pd.DataFrame]]:
    """Clean the data in the specified data files and DataFrames.

    Args:
        data_frames (dict[str, list[pd.DataFrame]]): Dictionary of DataFrames, where the keys are the class names
            and the values are lists of DataFrames for that class to clean.
        schema (SchemaView | str | Path): The schema that the data belong to. It should contain classes
            for all the classes in data_frames.
        log_file (str | Path): The Excel (.xlsx) file to save the log of changes to. If None then no log file
            is saved.
        clean_operations (list[dict[str, Any]]): List of cleaning operations to perform. These are performed in order.
            Each item is a dictionary where the key is the operation name and the value is the parameters for that
            operation. The format of the parameters depends on the operation.

    Returns:
        dict[str, list[pd.DataFrame]]: Dictionary where the keys are the class names and the values are lists
                    of DataFrames that are cleaned.
    """
    cleaner = DataCleaner(schema=schema)
    _, data_frames = cleaner.clean_data(
        data_files=None,
        data_frames=data_frames,
        output_dir=None,
        log_file=log_file,
        clean_operations=clean_operations,
    )
    return data_frames
