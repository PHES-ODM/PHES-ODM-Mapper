from pathlib import Path

import pandas as pd

from odm_map.mapper.map_data import DataMapper


def action_map_data(
    source_schema_file: str | Path,
    target_schema_file: str | Path,
    mappers_dir: str | Path,
    data_frames: dict[str, list[pd.DataFrame]],
    max_processes: int | None = 1,
    prepare_barid: str = "Preparing Data",
    map_barid: str = "Mapping",
    convert_barid: str = "Processing Data",
    keep_extra_columns: bool = True,
    keep_tracking_columns: bool = True,
    unrestricted_eval: bool = True,
) -> dict[str, list[pd.DataFrame]]:
    """Map all the data specified in data_frames using all mapper files found in the specified mapper directory.

    Args:
        source_schema_file (str | Path): The LinkML schema for the source database.
        target_schema_file (str | Path): The LinkML schema for the target database.
        mappers_dir (str | Path): The directory containing all LinkML Mapper configuration (YAML)
            files. All config files will be used for mapping all the loaded data.
        data_frames (dict[str, list[pd.DataFrame]]): Dictionary of source DataFrames to map. The keys are the
            source class names and the values are lists of DataFrames belonging to the class, which should each be mapped.
        max_processes (int | None, optional): Maximum number of processes to use for multi-processing.
            If 1 then no multi-processing will be performed. If None or 0 then the maximum number
            (as obtained by cpu_count()) will be used. Note that for mapping small tables multi-processing
            might be slower. Defaults to 1.
        prepare_barid (str, optional) The ID/title to give to the progress bar for preparing the data,
            before the initial mapping. Defaults to "Preparing Data",
        map_barid (str, optional) The ID/title to give the the progress bar for the mapping step.
            Defaults to "Mapping"
        convert_barid (str, optional) The ID/title to give to the progress bar for converting the mapped data
            to DataFrames. Defaults to "Processing Data".
        keep_extra_columns (bool, optional): If True, then keep the extra columns in the final DataFrame. These
            are columns that start with the string extra_and_tracking_slots.EXTRA_SLOT_PREFIX and end with the
            string extra_and_tracking_slots.EXTRA_SLOT_SUFFIX. If False then they are removed. Defaults to True.
        keep_tracking_columns (bool, optional): If True, then keep the tracking columns in the final DataFrame.
            These are columns that specify from which row and file/table each of the output rows was populated
            from. Tracking columns start with the string extra_and_tracking_slots.TRACKING_SLOT_PREFIX and end
            with the string extra_and_tracking_slots.TRACKING_SLOT_SUFFIX. If False then these columns are
            dropped. Defaults to True.

    Returns:
        dict[str, list[pd.DataFrame]]: Keys are the target class names and the values are the mapped data for
            that class.
    """
    mapper = DataMapper()
    data, _ = mapper.run(
        data_files=None,
        data_frames=data_frames,
        output_dir=None,
        source_schema_file=source_schema_file,
        target_schema_file=target_schema_file,
        mappers_dir=mappers_dir,
        max_processes=max_processes,
        prepare_barid=prepare_barid,
        map_barid=map_barid,
        convert_barid=convert_barid,
        keep_extra_columns=keep_extra_columns,
        keep_tracking_columns=keep_tracking_columns,
        unrestricted_eval=unrestricted_eval,
    )
    return data
