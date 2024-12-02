import os
from typing import Dict, List, Union, Optional
import pandas as pd
from datetime import datetime
from pathlib import Path

from odm_map.progress import ProgressCounter, EmptyCounter
from odm_map.utils.logger import get_logger
from odm_map.utils.general_utils import save_data_frame
from odm_map.utils.tracking_slots import drop_tracking_slots

logger = get_logger(__name__)


def action_save_data(
    data_frames: Dict[str, List[pd.DataFrame]],
    output_dir: Union[str, Path],
    progress_barid: Optional[str] = None,
    name_format: str = "{class_name}.csv",
    name_format_kwargs: Dict = {},
    keep_tracking_slots: bool = False,
    exception_if_exists: bool = False,
) -> Dict[str, List[str]]:
    """Save the specified DataFrames to disk.

    Args:
        data_frames (Dict[str, List[pd.DataFrame]]): The data to save. The keys are the class names and the values
            are lists of DataFrames belonging to the class. For each key, the list of DataFrames are concatenated
            into a single DataFrame.
        output_dir (Union[str, Path]): The directory to save the DataFrames to.
        progress_barid (Optional[str], optional): If set then the title of the progress bar to show while saving.
            If not set then do not show a progress bar.
        name_format (str, optional): The string interpolation format of the file names, accepts the variable class_name.
            Defaults to "{class_name}.csv"
        name_format_kwargs (Dict, optional): A dictionary of values that contain some additional arguments for
            string interpolation of name_format. This could include arguments such as "temp_dir" that can be
            used in formating name_format (eg. "{temp_dir}/file.csv"). These arguments are used in addition
            to arguments that this function calculates such as "class_name". Defaults to {}.
        keep_tracking_slots (bool, optional): If True then keep all tracking slots in the saved data. If False then
            all tracking slots are removed. Defaults to False.
        exception_if_exists (bool, optional): If True then raise an exception if a file already exists with the same
            name as a file we are trying to save. If False then overwrite the file. Defaults to False.

    Raises:
        ValueError: Only raised if exception_if_exists is True. The data could not be saved because one of the output
            files already exists. Be sure to delete the files in output_dir before callings save_data.

    Returns:
        Dict[str, List[str]]: A dictionary where the keys are class names and the values are lists
            of files saved to disk for that class.
    """
    # Save data to disk
    all_mapped_files = {}
    save_tic = datetime.now()
    if progress_barid:
        progress = ProgressCounter(
            {progress_barid: len(data_frames)}, multiple_bars=False
        )
    else:
        progress = EmptyCounter()

    with progress:
        for class_name, dfs in data_frames.items():
            # Combine the DataFrames into one
            df = pd.concat(dfs, ignore_index=True, axis=0)

            # Drop the tracking slots if requested
            if not keep_tracking_slots:
                df = drop_tracking_slots(df)

            # Determine the output file name, based on name_format and name_format_kwargs
            kwargs = name_format_kwargs.copy()
            kwargs.update({"class_name": class_name})
            output_data_file = os.path.join(output_dir, name_format.format(**kwargs))

            # Raise exception if exception_if_exists is True and the output file already exists
            if exception_if_exists and os.path.exists(output_data_file):
                raise ValueError(f"Output data file already exists: {output_data_file}")

            logger.debug(
                f"Saving merged mapped data file for {class_name} ({len(dfs)} source frame(s), {len(df.index)} rows): {output_data_file}"
            )
            save_data_frame(df, output_data_file, index=False)
            if class_name not in all_mapped_files:
                all_mapped_files[class_name] = []
            all_mapped_files[class_name].append(output_data_file)

            progress.update(progress_barid, 1)
    logger.debug(f"Total time for saving: {datetime.now() - save_tic}")
    logger.info(f"All data saved to directory: {output_dir}")

    return all_mapped_files
