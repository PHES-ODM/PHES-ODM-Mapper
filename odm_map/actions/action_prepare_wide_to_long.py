import os
from typing import Dict, List, Union
import pandas as pd
from pathlib import Path

from odm_map.prepare_wide_to_long.wide_column_expander import WideColumnExpander
from odm_map.prepare_wide_to_long.wide_column_map_maker import WideColumnMapMaker

SOURCE_CLASS_NAME = "wide_data"


def action_prepare_wide_to_long(
    data_frames: Dict[str, List[pd.DataFrame]],
    config: Union[str, Path],
    target_schema: Union[str, Path],
    output_dir: Union[str, Path],
    debug_mode: bool = False,
) -> Dict[str, List[pd.DataFrame]]:
    """Prepare the data to map from wide format to long format. This will rearrange the data to be
    in a format that is ready for wide to long mapping, will create multiple LinkML-Map mapping
    schemas to apply to the prepared data, and also create a LinkML schema for the prepared data
    to provide to a downstream map action. Usually the prepare_wide_to_long action is followed
    immediately by a map_data action.

    The generated LinkML-Map schemas are located in output_dir, while the LinkML schema is
    located at {output_dir}/schema/schema.yaml.

    Args:
        data_frames (Dict[str, List[pd.DataFrame]]): Dictionary of DataFrames in wide format that
            we want to prepare for mapping to long format. The keys are the class names and
            the values are lists of DataFrames belonging to the class. The class names are ignored,
            and all DataFrames for all classes are concatenated together into one large DataFrame.
            This DataFrame is then modified to prepare it for wide-to-long mapping.
        config (Union[str, Path]): The configuration file to use for the action.
        target_schema (Union[str, Path]): The target schema for the long format that we want
            to map to, such as ODM v3 long format.
        output_dir (Union[str, Path]): Directory to save all the artifacts required for wide-to-long
            mapping. This include the LinkML-Map schemas for mapping (in output_dir) and the
            LinkML schema used for the prepared dataset that gets returned to the caller
            (in {output_dir}/schema/schema.yaml).
        debug_mode (bool): If True then run in debug mode. In debug mode the expanded wide data
            is saved to output_dir/data/expanded.csv.

    Returns:
        Dict[str, List[pd.DataFrame]]: Dictionary of DataFrames based on the input data_frames that
            have been modified to be ready for mapping from wide to long format. The key is the
            wide-format class name (SOURCE_CLASS_NAME), and the value is a list of DataFrames
            belonging to the wide-format class. This data is ready to be mapped to long format
            using the LinkML-Map schemas saved to output_dir and the LinkML schema saved at
            {output_dir}/schema/schema.yaml.
    """
    # First expand the columns to be in tableShortName_attribute:index format
    expander = WideColumnExpander(
        config=config, source_class_name=SOURCE_CLASS_NAME, target_schema=target_schema
    )
    data_frames = [b for a in data_frames.values() for b in a]

    # Save expanded data as expanded_output_file if we're in debug mode
    expanded_output_file = (
        os.path.join(output_dir, "data", "expanded.csv")
        if output_dir and debug_mode
        else None
    )
    if expanded_output_file and os.path.dirname(expanded_output_file):
        os.makedirs(os.path.dirname(expanded_output_file), exist_ok=True)

    df = expander.expand(
        data_files=None, data_frames=data_frames, output_file=expanded_output_file
    )
    data_frames = {SOURCE_CLASS_NAME: [df]}

    # Create the LinkML-Map schemas and the LinkML schema for the prepared data in data_frames.
    maker = WideColumnMapMaker(
        config=config, source_class_name=SOURCE_CLASS_NAME, target_schema=target_schema
    )
    input_data_frame = data_frames[SOURCE_CLASS_NAME][0]
    maker.make(data_file=None, data_frame=input_data_frame, output_dir=output_dir)

    return data_frames
