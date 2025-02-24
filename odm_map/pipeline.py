"""
Map data using a transformation module.

```python
from pipeline import Pipeline

pipeline = Pipeline(
    module="odm-v1-to-v2",
    module_dir=None,
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
from typing import Union, Optional, List, Dict
from datetime import datetime
import tempfile
import pandas as pd

from linkml_runtime import SchemaView

from odm_map.actions.action_clean_data import action_clean_data
from odm_map.actions.action_save_data import action_save_data
from odm_map.actions.action_map_data import action_map_data
from odm_map.actions.action_generate_ids import action_generate_ids
from odm_map.actions.action_filter_data import action_filter_data
from odm_map.actions.action_expand_data import action_expand_data
from odm_map.utils.modules import (
    get_module_config,
    get_module_dir,
    MODULE_SOURCE_SCHEMA_KEY,
    MODULE_STEPS_KEY,
    MODULE_IF_KEY,
    MODULE_ACTION_KEY,
    MODULE_PARAMS_KEY,
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


class Pipeline(object):
    def __init__(
        self,
        module: Optional[str],
        module_dir: Optional[Union[str, Path]],
    ):
        """Class to perform a full mapping, including filtering and ID generation.

        Args:
            module (Optional[str]): The built-in module for the mapping, eg. "odm-v1-to-v2" or "nwss-reporting-to-v2".
                If None then module_dir must be specified.
            module_dir (Optional[Union[str, Path]]): The directory for the mapping module. If None then module must be specified.
        """
        # Tell the user which module we're using
        if module:
            logger.info(f"Running with module '{module}'")
        else:
            logger.info(f"Running with module directory {module_dir}")

        # Load the data mapping module
        self.config_file, self.config = get_module_config(
            module=module, module_dir=module_dir
        )
        self.module_dir = get_module_dir(module=module, module_dir=module_dir)

        # Load the source schema
        self.source_schema = self.get_module_path(self.config[MODULE_SOURCE_SCHEMA_KEY])
        self.source_schema = SchemaView(self.source_schema)

        all_classes = all_classes_without_tree_root(self.source_schema)
        all_classes = ", ".join(all_classes)
        logger.info(f"Recognized input tables are: {all_classes}")

    def get_module_path(self, path: str) -> Optional[Path]:
        if not path:
            return None
        return self.module_dir / path

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
            self.temp_dir = Path(temp_dir)
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
        top_level_kwargs = {
            "temp_dir": str(self.temp_dir),
            "output_dir": str(Path(output_dir)),
            "debug_mode": debug_mode,
        }
        # Go through each step of the module and perform each action
        for step in self.config[MODULE_STEPS_KEY]:
            action = step[MODULE_ACTION_KEY]

            # If there is an "if" section in the current step then only run the step if the "if" value
            # equates to either a non-zero integer, boolean True, or string "True" (case-insensitive).
            stepif = step.get(MODULE_IF_KEY, True)
            if isinstance(stepif, str):
                stepif = stepif.format(**top_level_kwargs)
            try:
                if not bool(int(stepif)):
                    continue
            except Exception:
                pass
            if str(stepif).lower() != "true":
                continue

            params = step.get(MODULE_PARAMS_KEY, {})

            if action == "clean":
                schema = self.get_module_path(params.get("schema"))
                clean_operations = params.get("operations", [])
                data_frames = action_clean_data(
                    data_frames=data_frames,
                    schema=schema,
                    clean_operations=clean_operations,
                )
            elif action == "expand":
                config = self.get_module_path(params.get("config"))
                data_frames = action_expand_data(
                    data_frames=data_frames,
                    config=config,
                )
            elif action == "save":
                progress_bar_title = params.get("progress_bar_title", None)
                output_dir = params.get("output_dir").format(**top_level_kwargs)
                output_name = params.get("output_name")
                _ = action_save_data(
                    data_frames=data_frames,
                    output_dir=output_dir,
                    progress_barid=progress_bar_title,
                    name_format=output_name,
                    name_format_kwargs=top_level_kwargs,
                    keep_tracking_slots=debug_mode,
                )
            elif action == "map":
                source_schema = self.get_module_path(params.get("source_schema"))
                target_schema = self.get_module_path(params.get("target_schema"))
                mappers_dir = self.get_module_path(params.get("mappers_dir"))
                prepare_bar_title = params.get("prepare_bar_title", "Preparing IDs")
                map_bar_title = params.get("map_bar_title", "Initial Mapping")
                data_frames = action_map_data(
                    source_schema_file=source_schema,
                    target_schema_file=target_schema,
                    mappers_dir=mappers_dir,
                    data_frames=data_frames,
                    max_processes=max_processes,
                    prepare_barid=prepare_bar_title,
                    map_barid=map_bar_title,
                )
            elif action == "generate_ids":
                # id_code can be a list. Each item of the list can be a single string (code_file)
                # or a dictionary with keys id_code and id_code_sheet
                top_id_code_file = params.get("id_code")
                top_id_code_sheet = params.get("id_code_sheet")
                id_code_files = []
                if top_id_code_file:
                    if isinstance(top_id_code_file, str):
                        # Single ID code file
                        id_code_files = [
                            {
                                "id_code_file": self.get_module_path(top_id_code_file),
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
                                        "id_code_file": self.get_module_path(
                                            cur_id_code
                                        ),
                                        "id_code_sheet": None,
                                    }
                                )
                            elif isinstance(cur_id_code, dict):
                                # Current entry is a dictionary with an id_code and id_code_sheet
                                id_code_files.append(
                                    {
                                        "id_code_file": self.get_module_path(
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

                id_config_file = self.get_module_path(params.get("id_config"))
                data_frames = action_generate_ids(
                    data_frames=data_frames,
                    id_config_file=id_config_file,
                    id_code_files=id_code_files,
                    multi_bar_progress=multi_bar_progress,
                    debug_mode=debug_mode,
                )
            elif action == "filter":
                filter_config_file = self.get_module_path(params.get("filters"))
                data_frames = action_filter_data(
                    data_frames=data_frames, filter_config_file=filter_config_file
                )
            else:
                raise CleanExitError(
                    f"Unrecognized action '{action}' in module configuration file {self.config_file}"
                )

        # Delete temporary directory
        if self.temp_dir_obj is not None:
            self.temp_dir_obj.cleanup()
            self.temp_dir_obj = None

        logger.info(f"Total runtime: {datetime.now() - tic}")

        return data_frames
