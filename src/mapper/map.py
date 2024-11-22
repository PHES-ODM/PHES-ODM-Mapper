# %%
"""
Map data using a transformation module.

```python
from mapper import Mapper

mapper = Mapper(
    module="odm_v1_to_v2",
    module_dir=None,
    debug_mode=False,
)

mapper.full_map(
    data_files={
        "measures": ["path/to/measures.csv"],
        "samples": ["path/to/samples.csv"],
        # ...
    },
    output_dir="../gen/odm_v1_to_v2",
)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pathlib import Path
from typing import Union, Optional, List, Dict
import os
import logging
from datetime import datetime
import tempfile
import argparse

from mapper.action_clean_data import action_clean_data
from mapper.action_save_data import action_save_data
from mapper.action_map_data import action_map_data
from mapper.action_generate_ids import action_generate_ids
from mapper.action_filter_data import action_filter_data

from mapper.modules import get_module_config, get_module_dir, MODULE_SOURCE_SCHEMA_KEY
from utils.logger import get_logger
from utils.general_utils import (
    load_data_with_tracking_columns,
)
from utils.clean_exit_error import CleanExitError
from utils.cli_utils import get_input_data_files

logger = get_logger(__name__)

# If True then if input_max_rows is specified then we load a random sample of input_max_rows
# rows. If False then we load the first input_max_rows rows. Should usually be False. Use
# True for debugging purposes.
RANDOM_SAMPLE_DATA = False

# Change the logging level of the Transformer. For very large datasets we will get way too many WARNINGs in
# the output.
for logger_name in [
    "linkml_map.transformer.object_transformer",
    "linkml_map.transformer.transformer",
    "linkml_runtime.utils.schemaview",
]:
    trlogger = logging.getLogger(logger_name)
    trlogger.setLevel("ERROR")


class Mapper(object):
    def __init__(
        self,
        module: Optional[str],
        module_dir: Optional[Union[str, Path]],
    ):
        """Class to perform a full mapping, including filtering and ID generation.

        Args:
            module (Optional[str]): The built-in module for the mapping, eg. "odm_v1_to_v2" or "nwss_reporting_to_v2".
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

    def get_module_path(self, path: str) -> Optional[Path]:
        if not path:
            return None
        return self.module_dir / path

    def full_map(
        self,
        data_files: Dict[str, List[Union[str, Path]]],
        output_dir: str,
        temp_dir: Union[str, Path] = None,
        input_max_rows: int = None,
        max_processes: int = 1,
        multi_bar_progress: bool = True,
        debug_mode: bool = False,
    ) -> Dict[str, List[Path]]:
        """Perform a full mapping, including filtering and ID generation.

        Args:
            data_files (Dict[str, List[Union[str, Path]]]): Dictionary specifying all source database data files
                to map. The keys are the source database class names and the values are lists of paths to the
                input data files for the class.
            output_dir (str): Directory to save all the final mapped data to.
            temp_dir (Union[str, Path], optional): Location to store all temporary files used by mapping.
                If None then a temporary directory will be created and deleted when complete. If set then
                the resulting temporary files will not be deleted. This is useful for debugging purposes.
                Defaults to None.
            input_max_rows (int, optional): Maximum number of input rows to load for mapping for each
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
            Dict[str, List[Path]]: Lists all final mapped files saved to disk. The keys are the output class
                names and the values are lists of file paths representing mapped data for the output class.
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

        source_schema = self.get_module_path(self.config[MODULE_SOURCE_SCHEMA_KEY])

        # Load all data
        data_frames = load_data_with_tracking_columns(
            data_files=data_files,
            max_rows=input_max_rows,
            schema=source_schema,
            random_sample_data=RANDOM_SAMPLE_DATA,
            add_all_tracking_columns=True,
            validate_class_names=True,
            validate_columns=True,
        )
        output_data_files = {}

        top_level_kwargs = {
            "temp_dir": str(self.temp_dir),
            "output_dir": str(Path(output_dir)),
            "debug_mode": debug_mode,
        }
        for step in self.config["steps"]:
            action = step["action"]
            stepif = step.get("if", True)
            if isinstance(stepif, str):
                stepif = stepif.format(**top_level_kwargs)
            try:
                if not bool(int(stepif)):
                    continue
            except Exception:
                pass
            if str(stepif).lower() != "true":
                continue
            params = step.get("params", {})

            if action == "clean":
                schema = self.get_module_path(params.get("schema"))
                data_frames = action_clean_data(data_frames=data_frames, schema=schema)
            elif action == "save":
                progress_id = params.get("progress_id", None)
                output_dir = params.get("output_dir").format(**top_level_kwargs)
                output_name = params.get("output_name")
                output_data_files = action_save_data(
                    data_frames=data_frames,
                    output_dir=output_dir,
                    progress_barid=progress_id,
                    name_format=output_name,
                    name_format_kwargs=top_level_kwargs,
                )
            elif action == "map":
                source_schema = self.get_module_path(params.get("source_schema"))
                target_schema = self.get_module_path(params.get("target_schema"))
                mapper_dir = self.get_module_path(params.get("mapper_dir"))
                prepare_barid = params.get("prepare_barid", "Preparing IDs")
                map_barid = params.get("map_barid", "Initial Mapping")
                data_frames = action_map_data(
                    source_schema_file=source_schema,
                    target_schema_file=target_schema,
                    mapper_dir=mapper_dir,
                    data_frames=data_frames,
                    max_processes=max_processes,
                    prepare_barid=prepare_barid,
                    map_barid=map_barid,
                )
            elif action == "generate_ids":
                id_code_file = self.get_module_path(params.get("id_code"))
                id_code_sheet = params.get("id_code_sheet")
                id_config_file = self.get_module_path(params.get("id_config"))
                data_frames = action_generate_ids(
                    data_frames=data_frames,
                    id_config_file=id_config_file,
                    id_code_file=id_code_file,
                    id_code_sheet=id_code_sheet,
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

        return output_data_files


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        class opts:
            # ODM v1 to v2
            # module = "odm_v1_to_v2"
            # module_dir = None
            # input_dir = "../../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated"
            # input_files = None  # ["WWMeasure", "../../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated/WWMeasure.csv"]
            # output_dir = "../../gen/odm_v1_to_v2-test"
            # temp_dir = "../../gen/odm_v1_to_v2-test/temp"

            # NWSS to v2
            module = "nwss_reporting_to_v2"
            module_dir = None
            # input_dir = "../../../../PHES-ODM-Data/nwss/private_renamed_test/"
            input_dir = "../../../../PHES-ODM-Data/nwss/nwss_renamed/"
            input_files = None # [ "nwss", "../../../../PHES-ODM-Data/nwss/private_renamed/nwss[cdc-nwss-restricted-data-set-wastewater-2024-03-19].csv" ]
            output_dir = "../../gen/nwss_reporting_to_v2-test"
            temp_dir = "../../gen/nwss_reporting_to_v2-test/temp"

            max_processes = 1
            input_max_rows = 50
            debug_mode = True
        # fmt: on
    else:
        args = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
        args.add_argument(
            "--module",
            type=str,
            help="The module name for the conversion. Either the 'module' or 'module-dir' command-line arguments must be provided (but not both). A module specifies the source dataset type, the target dataset type, and all required configuration for the conversion.",
            required=False,
        )
        args.add_argument(
            "--module-dir",
            type=str,
            help="The module directory for the conversion. Either the 'module' or 'module-dir' command-line arguments must be provided (but not both). A module specifies the source dataset type, the target dataset type, and all required configuration for the conversion.",
            required=False,
        )
        args.add_argument(
            "--input-dir",
            type=str,
            help="Directory containing all of the input data to map. The file names (without extension) correspond to the table name, with anything in square brackets ignored.",
            required=False,
        )
        args.add_argument(
            "--input-files",
            nargs="+",
            type=str,
            help="List of all input files and the source class for each file. Format is 'class_name file.csv [class_name2 file2.csv ...]'",
            required=False,
        )
        args.add_argument(
            "--output-dir",
            type=str,
            help="Directory to save all the mapped data to.",
            required=True,
        )
        args.add_argument(
            "--temp-dir",
            type=str,
            help="Directory to save all temporary files to. If specified then the temporary directory is not deleted after processing. If not specified then a system-specified temporary directory is used and deleted after processing. Primarily used for debugging.",
            required=False,
        )
        args.add_argument(
            "--input-max-rows",
            type=int,
            help="The maximum number of rows to map from each input data file. If 0 then map all rows.",
            default=0,
            required=False,
        )
        args.add_argument(
            "--max-processes",
            type=int,
            help="Maximum number of processes to run at a time for mapping the data. If non-positive then the max available processes are used.",
            default=1,
            required=False,
        )
        args.add_argument(
            "--debug-mode",
            action="store_true",
            help="If set then run ID generation in debug mode, which only affects what is included in the output data files. Debug data includes some additional columns (eg. original ID values, row number column for linking, primary key index and values, etc.). Debug output will also include any duplicated primary keys, with an additional 'drop' column specifying if it is a duplicate, in which case the row would be dropped when not in debug mode.",
        )
        opts = args.parse_args()

    tic = datetime.now()

    data_files = get_input_data_files(opts.input_files, opts.input_dir)

    mapper = Mapper(
        module=opts.module,
        module_dir=opts.module_dir,
        debug_mode=opts.debug_mode,
    )
    mapper.full_map(
        data_files=data_files,
        output_dir=opts.output_dir,
        temp_dir=opts.temp_dir,
        input_max_rows=opts.input_max_rows,
        max_processes=opts.max_processes,
        multi_bar_progress="get_ipython" not in globals(),
    )
