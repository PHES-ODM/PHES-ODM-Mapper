from pathlib import Path

import pandas as pd

from odm_map.column_dropper.drop_columns import DropColumns


def action_drop_columns(
    data_frames: dict[str, list[pd.DataFrame]],
    drop_extra_columns: bool = False,
    drop_tracking_columns: bool = False,
    keep_columns_in_schema_only: bool = False,
    schema: str | Path | None = None,
) -> dict[str, list[pd.DataFrame]]:
    """Drop specified columns from the DataFrames.

    Args:
        data_frames (dict[str, list[pd.DataFrame]]): Dictionary of DataFrames to drop columns from. The keys
            are the class names and the values are lists of DataFrames for the class.
        drop_extra_columns (bool, optional): If True then drop all extra columns from the DataFrames. Extra
            columns are the columns that begin with the string '_extra_'. Defaults to False.
        drop_tracking_columns (bool, optional): If True then drop all tracking columns from the DataFrames.
            Tracking columns are the columns that specify which source row number and class/table the row
            in the DataFrame was populated from. These are added during an upstream mapping operation.
            Defaults to False.
        keep_columns_in_schema_only (bool, optional): If True then only keep the columns that are recognized
            as valid columns for the class according to the LinkML schema (specified by the schema parameter).
            Defaults to False.
        schema (str | Path | None, optional): The schema to use if keep_columns_in_schema_only is True.
            If keep_columns_in_schema_only is False then this can be None. Defaults to None.

    Returns:
        dict[str, list[pd.DataFrame]]: The DataFrames with the specified columns dropped. This is a dictionary
            where the keys are the class names and the values are lists of DataFrames for the class.
    """
    drop = DropColumns()
    return drop.drop_columns(
        data_files=None,
        data_frames=data_frames,
        drop_extra_columns=drop_extra_columns,
        drop_tracking_columns=drop_tracking_columns,
        keep_columns_in_schema_only=keep_columns_in_schema_only,
        schema=schema,
    )
