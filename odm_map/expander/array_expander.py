"""
The ArrayExpander expands array values in a DataFrame, so that each item in the
array gets its own row. The array values can either be a YAML string (eg.
"['a','b','c']") that gets converted to an array, or an actual array.

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

The first two rows (Orange) were expanded from [1, "b"], while the last two
(Green) were expanded from [5, 6]. All values in the other columns are copied
over without modification (ie. the measure column).

Which table and which columns in those tables that are expanded are determined
by the configuration file, which is in the following format:

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

Each key in the `expand_columns` dictionary is a table name. The values are
arrays of columns within that table to expand.

Additional configuration options can also be specified, which are described below.

## select_items Option

An index or list of indices can be specified in the configuration
to specify which array elements should be selected and expanded (the other elements
get dropped). The following will select the first item in `sampleShed`:

```yaml
expand_columns:
    sites:
        - sampleShed:
            select_items: 0
```

The following will select the first and second items:

```yaml
expand_columns:
    sites:
        - sampleShed:
            select_items: [0, 1]
```

The following will select the last item:

```yaml
expand_columns:
    sites:
        - sampleShed:
            select_items: -1
```

After selection with `select_items`, the row then gets expanded using the selected
items.

If an index specified under `select_items` is out of range (either at or above
the array length, or below the negative array length) then that index is
removed and ignored. If an index is specified more than once (either as a negative or
positive index) then the duplicate indices are removed and ignored.

## remove_nulls Option

All Null items and empty strings can be removed from the array before selecting and
expanding. This is specified by setting the `remove_nulls` key to True:

```yaml
expand_columns:
    sites:
        - sampleShed:
            remove_nulls: True
            select_items: -1
```

For example, with the following sites table:

| sampleShed                   |
|------------------------------|
| ['hosptl', None, 'dorm', ''] |

Removing the null values will result in:

| sampleShed         |
|--------------------|
| ['hosptl', 'dorm'] |

## max_length Option

The `max_length` option does not modify any data. Instead, it logs an error message
to tell the user that an array has too many elements. A common example is if you
want to make sure that only one value is present in a certain column you would
set `max_length` to one, although any value is allowed. Below is an example
configuration:

```yaml
expand_columns:
    sites:
        - sampleShed:
            remove_nulls: True
            max_length: 1
```

If `remove_nulls` is also set to True, then the null values are removed first,
followed by checking the length with `max_length`.

If `select_items` is specified, then `max_length` is performed before selecting
the items.

## expand Option

The `expand` option (which defaults to True) will perform the actual expanding
of the rows and is performed after all other options are applied. If set to False,
then no new rows are created, but the array values are still processed (ie.
`remove_nulls`, `max_length`, and `select_items` are still applied). Setting
`expand` to False is useful if you just want to clean up the array values
without expanding them into multiple rows. Below is an example configuration:

```yaml
expand_columns:
    sites:
        - sampleShed:
            remove_nulls: True
            expand: False
```

The above will remove null values from the `sampleShed` column arrays, but will not
create any new rows and instead keep all the non-null values in the array.
"""

from typing import Union, List, Dict, Any, Optional, Tuple
from pathlib import Path
import yaml
import pandas as pd

from odm_map.utils.logger import get_logger
from odm_map.utils.general_utils import (
    load_data_frames_for_classes,
    save_data_frames_for_classes,
)
from odm_map.progress import ProgressCounter


# Config file keys
class ConfigKeys:
    EXPAND_COLUMNS = "expand_columns"
    SELECT_ITEMS = "select_items"
    MAX_LENGTH = "max_length"
    REMOVE_NULLS_KEY = "remove_nulls"
    EXPAND = "expand"


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
        if not self.config:
            logger.error("Config for ArrayExpander is empty or missing")
            return data_files, data_frames

        logger.info("Expanding data...")

        if not data_frames:
            data_frames = {}

        # Load files from disk
        load_data_frames_for_classes(data_files, data_frames, max_rows=max_rows)

        # If config has no columns to expand then return the data_frames unchanged
        if ConfigKeys.EXPAND_COLUMNS not in self.config:
            return data_files, data_frames

        # Count total expand operation to perform
        # total = (# of classes) * (# DataFrames in class) # (# columns to expand)
        total = 0
        for class_name, class_config in self.config[ConfigKeys.EXPAND_COLUMNS].items():
            if class_name not in data_frames:
                continue
            total += len(data_frames[class_name]) * len(class_config)

        progress = ProgressCounter({EXPAND_BARID: total}, multiple_bars=False)

        with progress:
            # Go through all classes to expand in the config file
            for class_name, class_config in self.config[
                ConfigKeys.EXPAND_COLUMNS
            ].items():
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
                                df,
                                column=cur_column,
                                config=cur_config,
                                class_name=class_name,
                            )
                            dfs.append(df)
                            progress.update(EXPAND_BARID, 1)
                        data_frames[class_name] = dfs

        # Save to disk if output_dir is specified
        data_files = None
        if output_dir:
            data_files = save_data_frames_for_classes(
                data_frames, output_dir, "{class_name}(expanded).csv"
            )

        return data_files, data_frames

    def expand_with_column(
        self,
        df: pd.DataFrame,
        column: str,
        config: Optional[Dict[str, Any]],
        class_name: str,
    ) -> pd.DataFrame:
        """Expand the DataFrame based on the specified column and the specified optional configuration.

        Args:
            df (pd.DataFrame): The DataFrame to expand.
            column (str): The column to use for expanding. We will look for arrays within this column and create
                rows for each value in the array.
            config (Optional[Dict[str, Any]]): Optional configuration for the expand operation. If None or empty,
                then we the output will have one row per value in the array. Otherwise expanding is done using
                the following config options:
                    ConfigKeys.REMOVE_NULLS_KEY: If True then before doing anything remove any null values from the arrays within
                        the columns being processed.
                    ConfigKeys.MAX_LENGTH: If set then an integer defining the maximum allowable length of an array before
                        any processing of the array is performed (but after nulls are removed if ConfigKeys.REMOVE_NULLS_KEY is True).
                        If an array is too large then an error is logged.
                    ConfigKeys.SELECT_ITEMS: Only select the item(s) at the specified index/indices in the resulting array for
                        expanding. For example: { ConfigKeys.SELECT_ITEMS: 0 } will only select the first item in the array,
                        and so the expanding will not add any additional rows. If an array, then additional rows will
                        be added. For example: { ConfigKeys.SELECT_ITEMS: [0, 3] } will only select the first (0) and fourth (3)
                        items in the array. If any of the indices are out of range then it is ignored. If none of the
                        indices are in range then the current row gets dropped. This is performed after ConfigKeys.REMOVE_NULLS_KEY
                        and ConfigKeys.MAX_LENGTH is performed.
            class_name (str): The class name of the DataFrame.

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

            if config and config.get(ConfigKeys.REMOVE_NULLS_KEY, False):
                # Remove null values from the array
                expanded_values = [
                    v for v in expanded_values if not pd.isna(v) and v != ""
                ]

            if config and ConfigKeys.MAX_LENGTH in config:
                # Make sure we have max_length or fewer items in the array
                max_length = config[ConfigKeys.MAX_LENGTH]
                if len(expanded_values) > max_length:
                    logger.error(
                        f"Row {idx + 1} of table for class {class_name}, slot {column}, has more than the maximum allowable {max_length} item{'' if max_length == 1 else 's'}: {expanded_values}"
                    )

            if config and ConfigKeys.SELECT_ITEMS in config:
                # Only expand selected items
                select_items = config[ConfigKeys.SELECT_ITEMS]
                if not isinstance(select_items, list):
                    select_items = [select_items]
                # Drop indices that are out of range (above the upper limit)
                select_items = [i for i in select_items if i < len(expanded_values)]
                # Drop indices that are out of range (below the lower limit)
                select_items = [i for i in select_items if i >= -len(expanded_values)]
                # Convert negative indices to positive
                select_items = [i % len(expanded_values) for i in select_items]
                # Drop duplicate indices
                select_items = list(dict.fromkeys(select_items))
                expanded_values = [
                    expanded_values[i] for i in select_items if i < len(expanded_values)
                ]

            # @TODO: Not sure if we want to drop rows with empty arrays anymore. For now
            # we shouldn't drop the rows (ie. code below is commented out). We might want
            # to add a configuration option to allow dropping rows, but that may not be
            # necessary and could just make things more confusing in the config file.
            # If there are no expanded values then we will drop the current row
            # if len(expanded_values) == 0:
            #     logger.info(
            #         f"No expanded values found for row {idx}, row will be dropped"
            #     )
            #     drop_rows.append(idx)
            #     continue

            # Go through each expanded value and create the row for it. The first expanded
            # value will be assigned to the original row already in the DataFrame.
            if config and config.get(ConfigKeys.EXPAND, True):
                df.loc[idx, column] = (
                    expanded_values[0] if len(expanded_values) else None
                )
                for expanded_value in expanded_values[1:]:
                    new_row = row.copy()
                    new_row[column] = expanded_value
                    new_rows.append(new_row)
            else:
                df.at[idx, column] = expanded_values

        # Drop all rows in drop_rows (drop_rows is an array of row indices to drop)
        if len(drop_rows) > 0:
            # Keep rows at indices that are NOT in drop_rows
            keep_rows = [i for i in df.index if i not in drop_rows]
            df = df.loc[keep_rows]

        # Append the new rows and sort
        if new_rows:
            new_rows_df = pd.DataFrame(new_rows)
            df = pd.concat([df, new_rows_df]).sort_index().reset_index(drop=True)

        return df
