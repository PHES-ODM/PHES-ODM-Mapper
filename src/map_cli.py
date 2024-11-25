# %%
"""
# Command-Line

To map data from the command-line, execute the following for ODM v1 to ODM v2 (replacing values
where appropriate):

```console
cd src
python3 map_cli.py \
    --module odm-v1-to-v2 \
    --input-dir "path/to/input/data" \
    --output-dir "../gen/odm-v1-to-v2"
```
"""

import argparse
from datetime import datetime
import sys

from mapper import Mapper
from mapper.modules import get_source_schema, get_all_modules
from utils.logger import get_logger
from utils.cli_utils import get_input_data_files
from utils.clean_exit_error import CleanExitError

if __name__ == "__main__":
    logger = get_logger(__name__)

    if "get_ipython" in globals():
        # fmt: off
        class opts:
            # ODM v1 to v2
            # module = "odm-v1-to-v2"
            # module_dir = None
            # # input_dir = "../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated"
            # input_dir = "../../../PHES-ODM-Data/odm_v1_data/excel/excel"
            # # input_dir = "/Users/martinwellman/Documents/Health/Wastewater/sars-cov-2-data/CSV/Ottawa"
            # input_files = None #["Sample", "../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated/Sample.csv"]
            # output_dir = "../gen/odm-v1-to-v2-test-new"
            # temp_dir = None #"../gen/odm-v1-to-v2-test-excel/temp"

            # NWSS to v2
            module = "nwss-reporting-to-v2"
            module_dir = None
            # input_dir = "../../../PHES-ODM-Data/nwss/private_renamed_test/"
            input_dir = "../../../PHES-ODM-Data/nwss/nwss_renamed/"
            # input_dir = "../../../PHES-ODM-Data/nwss/nwss_renamed_excel/"
            # input_dir = "/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Data/nwss/nwss_renamed_excel"
            input_files = None # [ "nwss", "../../../PHES-ODM-Data/nwss/private_renamed/nwss[cdc-nwss-restricted-data-set-wastewater-2024-03-19].csv" ]
            output_dir = "../gen/nwss-reporting-to-v2-test"
            temp_dir = None #"../gen/nwss-reporting-to-v2-xl3/temp"

            max_processes = 2
            input_max_rows = None
            debug_mode = False
        # fmt: on
    else:
        args = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
        module_group = args.add_mutually_exclusive_group(required=True)
        module_group.add_argument(
            "--module",
            type=str,
            help="The module name for the conversion. Either the 'module' or 'module-dir' command-line arguments must be provided (but not both). A module specifies the source dataset type and the target dataset type to map to.",
            choices=get_all_modules(),
            required=False,
        )
        module_group.add_argument(
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

    try:
        logger.info(f"Starting run at {datetime.now()}")

        source_schema = get_source_schema(opts.module, opts.module_dir)
        data_files = get_input_data_files(
            opts.input_files, opts.input_dir, schema=source_schema
        )

        mapper = Mapper(
            module=opts.module,
            module_dir=opts.module_dir,
        )
        mapper.full_map(
            data_files=data_files,
            output_dir=opts.output_dir,
            temp_dir=opts.temp_dir,
            input_max_rows=opts.input_max_rows,
            max_processes=opts.max_processes,
            multi_bar_progress="get_ipython" not in globals(),
            debug_mode=opts.debug_mode,
        )
    except CleanExitError as e:
        logger.error(str(e))
        if "get_ipython" not in globals():
            sys.exit(1)
    except KeyboardInterrupt:
        logger.error("Interrupted by user")
        if "get_ipython" not in globals():
            sys.exit(1)
