# %%
"""
The ArrayExpander expands array values in a DataFrame, so that each item in the array gets its own row. The array values
can either be a YAML string (eg. "['a','b','c']") that gets converted to an array, or an actual array.

For example, using the following table:

| measure | value    |
|---------|----------|
| Orange  | [1, "b"] |
| Blue    | 3        |
| Green   | [5, 6]   |

When expanded based on the "value" column, we get the following table:

| measure | value    |
|---------|----------|
| Orange  | 1        |
| Orange  | b        |
| Blue    | 3        |
| Green   | 5        |
| Green   | 6        |

Which table and which columns in those tables that are expanded are determined by the configuration file, which is
in the following format:

```yaml
expand_columns:
    instruments:
        - name
        - manufacturer
    measures:
        - value
    samples:
        - repType
        - saMaterial
    sites:
        - sampleShed
    # ...
```

Each key in the `expand_columns` dictionary is a table name. The values are arrays of columns within that table to expand.

"""

import os
from typing import Union, List, Dict, Any, Optional, Tuple
from pathlib import Path
import yaml
import pandas as pd

from odm_map.utils.logger import get_logger
from odm_map.utils.general_utils import read_data_frame, save_data_frame
from odm_map.progress import ProgressCounter

# Config file keys
EXPAND_COLUMNS_KEY = "expand_columns"
SELECT_ITEM_KEY = "select_item"

EXPAND_BARID = "Expanding"

logger = get_logger(__name__)


class ArrayExpander(object):
    def __init__(self, config: Union[str, Path]):
        with open(config, "r") as f:
            self.config = yaml.safe_load(f)

    def expand_data(
        self,
        data_files: Dict[str, List[Union[str, Path, Dict]]],
        data_frames: Dict[str, List[pd.DataFrame]],
        output_dir: Optional[Union[str, Path]] = None,
        max_rows: int = 0,
    ) -> Tuple[Dict[str, List[str]], Dict[str, List[pd.DataFrame]]]:
        """Expand all the specified data files and DataFrames, and optionally save them to disk.

        Args:
            data_files (Dict[str, List[Union[str, Path, Dict]]]): A dictionary specifying files and DataFrames to expand. The
                keys are class names and the values are paths to files to expand. Can be combined with the data_frames
                parameter to expand both files and DataFrames.
            data_frames (Dict[str, List[pd.DataFrame]]): A dicitonary specifying DataFrames to expand. The keys are the class
                names and the values are lists of DataFrames belonging to that class. Can be combined with the data_files
                parameter to expand both files and DataFrames.
            output_dir (Optional[Union[str, Path]], optional): If specified then save the resulting DataFrames to disk.
                DataFrames belonging to the same class are merged so that only one file per class is saved.
            max_rows (int, optional): If positive then the number of rows to load from each data file. If 0 then
                all rows are loaded. Defaults to 0.

        Returns:
            Tuple[Dict[str, List[str]], Dict[str, List[pd.DataFrame]]]: A tuple of [expanded_data_files, expanded_data_frames]:
                expanded_data_files: Dictionary of all outputed expanded data files. The keys are the class name
                    the file belongs to and the values are lists of files. If output_dir is None then data_files will be
                    None (ie. no data saved to disk), instead see expanded_data_frames.
                expanded_data_frames: Dictionary of all expanded DataFrames. The keys are the class names and the
                    values are lists of cleaned DataFrames.
        """
        logger.info("Expanding data")

        if not data_frames:
            data_frames = {}

        # Load files from disk
        if data_files:
            for class_name, class_files in data_files.items():
                if class_name not in data_frames:
                    data_frames[class_name] = []
                for class_file in class_files:
                    df = read_data_frame(
                        class_file,
                        nrows=max_rows if max_rows and max_rows > 0 else None,
                        keep_default_na=False,
                        na_values=None,
                    )
                    data_frames[class_name].append(df)

        # If config has no columns to expand then return the data_frames unchanged
        if EXPAND_COLUMNS_KEY not in self.config:
            return data_frames

        # Count total expand operation to perform
        # total = (# of classes) * (# DataFrames in class) # (# columns to expand)
        total = 0
        for class_name, class_config in self.config[EXPAND_COLUMNS_KEY].items():
            if class_name not in data_frames:
                continue
            total += len(data_frames[class_name]) * len(class_config)

        progress = ProgressCounter({EXPAND_BARID: total}, multiple_bars=False)

        with progress:
            # Go through all classes to expand in the config file
            for class_name, class_config in self.config[EXPAND_COLUMNS_KEY].items():
                if class_name not in data_frames:
                    continue
                # Go through all the column configs in the config file
                for column_config in class_config:
                    if isinstance(column_config, str):
                        column_config = {column_config: None}
                    # Expand based on the column coniguration
                    for cur_column, cur_config in column_config.items():
                        dfs = []
                        for df in data_frames[class_name]:
                            df = self.expand_with_column(
                                df, column=cur_column, config=cur_config
                            )
                            dfs.append(df)
                            progress.update(EXPAND_BARID, 1)
                        data_frames[class_name] = dfs

        # Save to disk if output_dir is specified
        data_files = None
        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            data_files = {}
            for class_name, dfs in data_frames.items():
                if class_name not in data_files:
                    data_files[class_name] = []
                df = pd.concat(dfs)
                output_file = Path(output_dir) / f"{class_name}(expanded).csv"
                data_files[class_name].append(output_file)
                save_data_frame(df, output_file, index=False)

        return data_files, data_frames

    def expand_with_column(
        self, df: pd.DataFrame, column: str, config: Optional[Dict[str, Any]]
    ) -> pd.DataFrame:
        """Expand the DataFrame based on the specified column and the specified optional configuration.

        Args:
            df (pd.DataFrame): The DataFrame to expand.
            column (str): The column to use for expanding. We will look for arrays within this column and create
                rows for each value in the array.
            config (Optional[Dict[str, Any]]): Optional configuration for the expand operation. If None or empty,
                then we the output will have one row per value in the array. Otherwise expanding is done using
                the following config options:
                    SELECT_ITEM_KEY: Only select the item(s) at the specified index/indices in the resulting array for
                        expanding. For example: { SELECT_ITEM_KEY: 0 } will only select the first item in the array,
                        and so the expanding will not add any additional rows. If an array, then additional rows will
                        be added. For example: { SELECT_ITEM_KEY: [0, 3] } will only select the first (0) and fourth (3)
                        items in the array. If any of the indices are out of range then it is ignored. If none of the
                        indices are in range then the current row gets dropped.

        Returns:
            pd.DataFrame: A copy of the DataFrame with the column expanded according to the configuration.
        """
        df = df.copy()
        new_rows = []
        drop_rows = []
        for idx, row in df.iterrows():
            val = row[column]

            if isinstance(val, list):
                expanded_values = val
            elif isinstance(val, str) and val.startswith("[") and val.endswith("]"):
                # Try to convert the string into an array
                try:
                    expanded_values = yaml.safe_load(val)
                    if not isinstance(expanded_values, list):
                        continue
                except Exception:
                    continue
            else:
                continue

            if config and SELECT_ITEM_KEY in config:
                # Only expand selected items
                select_item = config[SELECT_ITEM_KEY]
                if not isinstance(select_item, list):
                    select_item = [select_item]
                expanded_values = [
                    expanded_values[i] for i in select_item if i < len(expanded_values)
                ]

            # If there are no expanded values then we will drop the current row
            if len(expanded_values) == 0:
                logger.info(
                    f"No expanded values found for row {idx}, row will be dropped"
                )
                drop_rows.append(idx)
                continue

            # Go through each expanded value and create the row for it. The first expanded
            # value will be assigned to the original row already in the DataFrame.
            df.loc[idx, column] = expanded_values[0]
            for expanded_value in expanded_values[1:]:
                new_row = row.copy()
                new_row[column] = expanded_value
                new_rows.append(new_row)

        # Drop all rows in drop_rows
        keep_rows = [i for i in df.index if i not in drop_rows]
        df = df.loc[keep_rows]

        # Append the new rows and sort
        new_rows_df = pd.DataFrame(new_rows)
        df = pd.concat([df, new_rows_df]).sort_index().reset_index(drop=True)

        return df
