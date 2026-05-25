"""
Map data using a transformation module.

```python
from pipeline import Pipeline

pipeline = Pipeline(
    module="odm-v1-to-v2",
    module_path=None,
)

pipeline.run(
    data_files={
        "measures": ["path/to/measures.csv"],
        "samples": ["path/to/samples.csv"],
        # ...
    },
    output_dir="../gen/odm-v1-to-v2",
)
"""

from pathlib import Path
from typing import Union, Optional, List, Dict, Any
from datetime import datetime
import tempfile
import pandas as pd

from odm_map.actions.action_drop_columns import action_drop_columns
from odm_map.actions.action_clean_data import action_clean_data
from odm_map.actions.action_save_data import action_save_data
from odm_map.actions.action_map_data import action_map_data
from odm_map.actions.action_generate_ids import action_generate_ids
from odm_map.actions.action_filter_data import action_filter_data
from odm_map.actions.action_expand_data import action_expand_data
from odm_map.actions.action_select_enum_hierarchy import action_select_enum_hierarchy
from odm_map.actions.action_prepare_wide_to_long import action_prepare_wide_to_long
from odm_map.utils.pipeline_module import (
    PipelineModule,
    MODULE_STEPS_KEY,
    MODULE_IF_KEY,
    MODULE_ACTION_KEY,
    MODULE_PARAMS_KEY,
    TEMP_DIR_TAG,
)
from odm_map.utils.logger import get_logger
from odm_map.utils.clean_exit_error import CleanExitError
from odm_map.utils.extra_and_tracking_slots import (
    load_data_with_source_tracking_columns,
)
from odm_map.utils.schema_utils import all_classes_without_tree_root

logger = get_logger(__name__)

# For loading data progress bar
LOADING_BARID = "Loading Data"

# Key for mark_instead_of_drop for filter operation. If this is True then instead of dropping items
# we set the ____drop column to TRUE
MARK_INSTEAD_OF_DROP_KEY = "mark_instead_of_drop"


class Pipeline(object):
    def __init__(
        self,
        module: Optional[Union[str, PipelineModule]],
        module_path: Optional[Union[str, Path]],
    ):
        """Class to perform a full mapping, including filtering and ID generation.

        Args:
            module (Optional[Union[str, PipelineModule]]): Either the name of the built-in module for the mapping
                (eg. "odm-v1-to-v2" or "nwss-reporting-to-v2") or an already loaded PipelineModule. If None then
                module_path must be specified.
            module_path (Optional[Union[str, Path]]): The path to the directory or zip file for the mapping module.
                If None then module  must be specified.
        """
        if isinstance(module, PipelineModule):
            self.module = module
        else:
            self.module = PipelineModule(module=module, module_path=module_path)

        # Tell the user which module we're using
        logger.info(f"Running with module '{module}'")

        # Load the source schema
        self.source_schema = self.module.get_source_schema_view()

        all_classes = all_classes_without_tree_root(self.source_schema)
        all_classes = ", ".join(all_classes)
        logger.info(f"Recognized input tables are: {all_classes}")

        self.temp_dir_obj = None

    def __del__(self):
        if self.temp_dir_obj is not None:
            self.temp_dir_obj.cleanup()
            self.temp_dir_obj = None

    def get_formatted_bool_key(self, d: Dict, key: str, default: Any = None) -> bool:
        val = self.get_formatted_string_key(d, key, default)
        if isinstance(val, str):
            return str(val).lower() in ("true", "1", "yes")
        return bool(int(val))

    def get_formatted_string_key(
        self, d: Dict, key: str, default: Any = None
    ) -> Optional[str]:
        val = d.get(key, default)
        if isinstance(val, str):
            val = val.format(**self.top_level_kwargs)
        if pd.isna(val):
            return None
        return str(val)

    def run(
        self,
        data_files: Dict[str, List[Union[str, Path, Dict[str, str]]]],
        output_dir: str,
        temp_dir: Union[str, Path] = None,
        max_rows: int = None,
        max_processes: int = 1,
        multi_bar_progress: bool = True,
        debug_mode: bool = False,
    ) -> Dict[str, List[pd.DataFrame]]:
        """Perform a full mapping, including filtering and ID generation.

        Args:
            data_files (Dict[str, List[Union[str, Path]]]): Dictionary specifying all source database data
                files to map. The keys are the data file class names and the values are a list of files to
                filter belonging to the class, or dictionaries for Excel files in the format
                {EXCEL_FILE_KEY: "file.xlsx", EXCEL_SHEET_KEY: "sheet_name"}.
            output_dir (str): Directory to save all the final mapped data to.
            temp_dir (Union[str, Path], optional): Location to store all temporary files used by mapping.
                If None then a temporary directory will be created and deleted when complete. If set then
                the resulting temporary files will not be deleted. This is useful for debugging purposes.
                Defaults to None.
            max_rows (int, optional): Maximum number of input rows to load for mapping for each
                data file specified in data_files. Defaults to None.
            max_processes (int, optional): Maximum number of processes to run to do the mapping. For large
                datasets increasing this can increase performance. Defaults to 1.
            multi_bar_progress (bool, optional): If True then output multiple progress bars at the same time
                when appropriate. If False then only show one progress bar at a time. Defaults to True.
            debug_mode (bool, optional): If True then run the ID generator in debug mode. Debug mode will result
                in the output mapped data to include various columns that were used during ID generation
                (such as the source database class name and row number used for populating a row, the original
                unmodified IDs before generation occurred, etc.), and will also not drop rows where duplicate
                primary keys are found, instead an additional column named "__drop" will be added to the output
                and set to TRUE if the row would be dropped when not in debug mode. Defaults to False.

        Returns:
            Dict[str, List[pd.DataFrame]]: Lists all final DataFrames that resulted from the mapping. The keys
                are the output class names and the values are lists of mapped DataFrames for the class.
        """
        tic = datetime.now()

        output_dir = Path(output_dir)

        # Prepare temporary directory
        if not temp_dir:
            self.temp_dir_obj = tempfile.TemporaryDirectory()
            self.temp_dir = Path(self.temp_dir_obj.name)
        else:
            self.temp_dir_obj = None
            self.temp_dir = Path(temp_dir).resolve()
        self.module.set_temp_dir(self.temp_dir)
        logger.debug(f"Using temporary directory {self.temp_dir}")

        # Load all data
        data_frames = load_data_with_source_tracking_columns(
            data_files=data_files,
            max_rows=max_rows,
            schema=self.source_schema,
            progress_barid=LOADING_BARID,
            validate_class_names=True,
        )

        # Values used for string interpolation (eg. for output paths). Some actions will
        # add additional values to this.
        self.top_level_kwargs = {
            TEMP_DIR_TAG.strip("{}"): str(self.temp_dir),
            "output_dir": str(Path(output_dir)),
            "debug_mode": debug_mode,
            "not_debug_mode": not debug_mode,
        }
        # Go through each step of the module and perform each action
        for step in self.module.config.get(MODULE_STEPS_KEY):
            action = step[MODULE_ACTION_KEY]

            # If there is an "if" section in the current step then only run the step if the "if" value
            # equates to either a non-zero integer, boolean True, or string "True" (case-insensitive).
            if not self.get_formatted_bool_key(step, MODULE_IF_KEY, True):
                continue

            params = step.get(MODULE_PARAMS_KEY, {})

            if action == "clean":
                schema = self.module.get_module_path(params.get("schema"))
                clean_operations = params.get("operations", [])
                log_file = self.get_formatted_string_key(params, "log_file")
                data_frames = action_clean_data(
                    data_frames=data_frames,
                    schema=schema,
                    log_file=log_file,
                    clean_operations=clean_operations,
                )
            elif action == "drop_columns":
                drop_extra_columns = self.get_formatted_bool_key(
                    params, "drop_extra_columns", False
                )
                drop_tracking_columns = self.get_formatted_bool_key(
                    params, "drop_tracking_columns", False
                )
                keep_columns_in_schema_only = self.get_formatted_bool_key(
                    params, "keep_columns_in_schema_only", False
                )
                schema = self.module.get_module_path(params.get("schema"))
                data_frames = action_drop_columns(
                    data_frames=data_frames,
                    drop_extra_columns=drop_extra_columns,
                    drop_tracking_columns=drop_tracking_columns,
                    keep_columns_in_schema_only=keep_columns_in_schema_only,
                    schema=schema,
                )
            elif action == "expand":
                config = self.module.get_module_path(params.get("config"))
                data_frames = action_expand_data(
                    data_frames=data_frames,
                    config=config,
                )
            elif action == "save":
                progress_bar_title = self.get_formatted_string_key(
                    params, "progress_bar_title", None
                )
                step_output_dir = self.get_formatted_string_key(params, "output_dir")
                # Do not format output_name, it will be format for tags like {class_name} in action_save_data.
                output_name = params.get("output_name")
                _ = action_save_data(
                    data_frames=data_frames,
                    output_dir=step_output_dir,
                    progress_barid=progress_bar_title,
                    name_format=output_name,
                    name_format_kwargs=self.top_level_kwargs,
                )
            elif action == "map":
                source_schema = self.module.get_module_path(params.get("source_schema"))
                target_schema = self.module.get_module_path(params.get("target_schema"))
                mappers_dir = self.module.get_module_path(params.get("mappers_dir"))
                prepare_bar_title = self.get_formatted_string_key(
                    params, "prepare_bar_title", "Preparing IDs"
                )
                map_bar_title = self.get_formatted_string_key(
                    params, "map_bar_title", "Initial Mapping"
                )
                data_frames = action_map_data(
                    source_schema_file=source_schema,
                    target_schema_file=target_schema,
                    mappers_dir=mappers_dir,
                    data_frames=data_frames,
                    max_processes=max_processes,
                    prepare_barid=prepare_bar_title,
                    map_barid=map_bar_title,
                    keep_extra_columns=True,
                    keep_tracking_columns=True,
                )
            elif action == "generate_ids":
                # id_code can be a list. Each item of the list can be a single string (code_file)
                # or a dictionary with keys id_code and id_code_sheet
                top_id_code_file = params.get("id_code")
                top_id_code_sheet = params.get("id_code_sheet")
                schema = self.module.get_module_path(params.get("schema"))
                id_code_files = []
                if top_id_code_file:
                    if isinstance(top_id_code_file, str):
                        # Single ID code file
                        id_code_files = [
                            {
                                "id_code_file": self.module.get_module_path(
                                    top_id_code_file
                                ),
                                "id_code_sheet": top_id_code_sheet,
                            }
                        ]
                    elif isinstance(top_id_code_file, list):
                        # Multiple ID code files
                        for cur_id_code in top_id_code_file:
                            if isinstance(cur_id_code, str):
                                # Current entry is a single ID code file string, with no sheet specified
                                id_code_files.append(
                                    {
                                        "id_code_file": self.module.get_module_path(
                                            cur_id_code
                                        ),
                                        "id_code_sheet": None,
                                    }
                                )
                            elif isinstance(cur_id_code, dict):
                                # Current entry is a dictionary with an id_code and id_code_sheet
                                id_code_files.append(
                                    {
                                        "id_code_file": self.module.get_module_path(
                                            cur_id_code.get("id_code")
                                        ),
                                        "id_code_sheet": cur_id_code.get(
                                            "id_code_sheet"
                                        ),
                                    }
                                )
                if len(id_code_files) == 0:
                    raise ValueError(
                        "Parameters for generate_ids must have at least one id_code entry"
                    )

                id_config_file = self.module.get_module_path(params.get("id_config"))
                data_frames = action_generate_ids(
                    data_frames=data_frames,
                    id_config_file=id_config_file,
                    id_code_files=id_code_files,
                    schema=schema,
                    multi_bar_progress=multi_bar_progress,
                    keep_extra_columns=True,
                    keep_tracking_columns=True,
                    debug_mode=debug_mode,
                )
            elif action == "filter":
                filter_config_file = self.module.get_module_path(params.get("filters"))
                mark_instead_of_drop = self.get_formatted_bool_key(
                    params, MARK_INSTEAD_OF_DROP_KEY, False
                )
                data_frames = action_filter_data(
                    data_frames=data_frames,
                    filter_config_file=filter_config_file,
                    debug_mode=mark_instead_of_drop,
                )
            elif action == "select_enum_hierarchy":
                schema = self.module.get_module_path(params.get("schema"))
                config = self.module.get_module_path(params.get("config"))
                data_frames = action_select_enum_hierarchy(
                    data_frames=data_frames, schema=schema, config=config
                )
            elif action == "prepare_wide_to_long":
                config = self.module.get_module_path(params.get("config"))
                target_schema = self.module.get_module_path(params.get("target_schema"))
                step_output_dir = self.get_formatted_string_key(params, "output_dir")
                data_frames = action_prepare_wide_to_long(
                    data_frames=data_frames,
                    config=config,
                    target_schema=target_schema,
                    output_dir=step_output_dir,
                    debug_mode=debug_mode,
                )
            else:
                raise CleanExitError(
                    f"Unrecognized action '{action}' in module configuration file {self.module.get_module_config_path()}"
                )

        # Delete temporary directory
        if self.temp_dir_obj is not None:
            self.temp_dir_obj.cleanup()
            self.temp_dir_obj = None

        logger.info(f"Total runtime: {datetime.now() - tic}")

        return data_frames
