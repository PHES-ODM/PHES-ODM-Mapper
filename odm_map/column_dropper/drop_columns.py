"""
Drop columns from DataFrames, either loaded from disk or already in memory. The columns that
get dropped can include:

1) Extra columns. These are columns that begin with the string _extra_. They are typically added
in an upstream mapping operation.
2) Tracking columns. These are columns that specify which row number and class/table that a row in
a DataFrame was populated from. They are typically added in an upstream mapping operation.
3) Any column that is not a recognized column according to a LinkML schema.

## Usage

```python
data_files = {
    "measures": ["measures1.csv", "measures2.csv"],
    "measureSets": ["measureSets1.csv", measureSets2.csv"],
    # etc.
}
drop = DropColumns()
drop.drop_columns(
    data_files=data_files,
    data_frames=None,
    drop_extra_columns=False,
    drop_tracking_columns=False,
    keep_columns_in_schema_only=True,
    output_dir="dropped/data",
    max_rows=0,
    schema="schemas/odm_v3.yaml",
)
```
"""

from typing import Dict, List, Union, Optional
from pathlib import Path
import pandas as pd
from linkml_runtime import SchemaView

from odm_map.utils.logger import get_logger
from odm_map.utils.extra_and_tracking_slots import is_extra_slot, is_tracking_slot
from odm_map.utils.general_utils import (
    load_data_frames_for_classes,
    save_data_frames_for_classes,
)

logger = get_logger(__name__)


class DropColumns:
    def __init__(self):
        pass

    def drop_columns(
        self,
        data_files: Dict[str, List[Union[str, Path, Dict]]],
        data_frames: Dict[str, List[pd.DataFrame]],
        drop_extra_columns: bool = False,
        drop_tracking_columns: bool = False,
        keep_columns_in_schema_only: bool = False,
        output_dir: Optional[Union[str, Path]] = None,
        max_rows: Optional[int] = None,
        schema: Optional[Union[SchemaView, Path, str]] = None,
    ) -> Dict[str, List[pd.DataFrame]]:
        """Drop columns from the specified DataFrames or data files according to the rules specified by the
        parameters. This can include dropping extra columns (ie. columns starting with "_extra_"), dropping
        tracking columns (ie. columns that specify which file and row number each row was loaded from), and
        dropping columns not recognized by a LinkML schema.

        Args:
            data_files (Dict[str, List[Union[str, Path, Dict]]]): Dictionary of files to load and drop columns
                from. The keys are the class names and the values are lists of files for the class. If a file
                is a dictionary, then it is an Excel file with a file path and a sheet name to load from the
                Excel file:
                    {
                        general_utils.EXCEL_FILE_KEY: "path/to/myfile.xlsx",
                        general_utils.EXCEL_SHEET_KEY: "mysheet",
                    }
            data_frames (Dict[str, List[pd.DataFrame]]): Dictionary of DataFrames to drop columns from. The keys
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
            output_dir (Optional[Union[str, Path]], optional): Optional directory to save the resulting data to.
                The file names are in the form "{class_name}.csv". Defaults to None.
            max_rows (Optional[int], optional): When loading the files in data_files, the maximum number of rows
                to load for each file. If None then all rows are loaded. Defaults to None.
            schema (Optional[Union[SchemaView, Path, str]], optional): If keep_columns_in_schema_only is True, then
                this is either the SchemaView or the path to the LinkML schema file. Only the columns
                recognized for the class in the schema are retained, all other columns are dropped. Defaults to None.

        Raises:
            ValueError: Exception raised if keep_columns_in_schema_only is True but not schema is specified.

        Returns:
            Dict[str, List[pd.DataFrame]]: Dictionary of all DataFrames with the columns dropped according to the
                parameters. The keys are the class names and the values are lists of DataFrames belonging to the
                class.
        """
        if isinstance(schema, (Path, str)):
            sv: SchemaView = SchemaView(schema)
        else:
            sv: SchemaView = schema

        if not data_frames:
            data_frames = {}

        # Load files from disk
        if data_files:
            logger.info("Loading data files to drop columns from")
            load_data_frames_for_classes(data_files, data_frames, max_rows=max_rows)

        # Go through all the classes in data_frames
        for class_name, dfs in data_frames.items():
            # Go through all the DataFrames for the current class
            logger.info(f"Dropping columns from class {class_name}")
            for idx in range(len(dfs)):
                df = dfs[idx]

                if keep_columns_in_schema_only:
                    # Only keep the columns that are recognized in the LinkML schema
                    if sv is None:
                        raise ValueError(
                            "Schema must be specified if keep_columns_in_schema_only is True, but None was given."
                        )
                    slot_defns = sv.class_induced_slots(class_name)
                    slots = [s.name for s in slot_defns]
                    df = df[[s for s in slots if s in df.columns]]
                else:
                    # Gather all columns to drop in drop_cols (extra and/or tracking columns)
                    drop_cols = []
                    if drop_extra_columns:
                        drop_cols.extend([c for c in df.columns if is_extra_slot(c)])
                    if drop_tracking_columns:
                        drop_cols.extend([c for c in df.columns if is_tracking_slot(c)])
                    if drop_cols:
                        # Drop the columns in drop_cols
                        df = df[[c for c in df.columns if c not in drop_cols]]

                # Save the DataFrame to return
                dfs[idx] = df

        if output_dir:
            save_data_frames_for_classes(
                data_frames, output_dir, file_name_format="{class_name}.csv"
            )

        return data_frames
