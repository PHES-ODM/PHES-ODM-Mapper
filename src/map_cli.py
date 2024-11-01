# %%
"""
# Command-Line

To map data from the command-line, execute the following for ODM v1 to ODM v2 (replacing values
where appropriate):

```console
cd src
python3 map_cli.py \
    --module odm_v1_to_v2 \
    --input_data_dir "path/to/input/data" \
    --output_dir "../gen/odm_v1_to_v2"
```
"""

import argparse
from datetime import datetime

from mapper import Mapper
from utils.cli_utils import get_input_data_files

if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        class opts:
            # ODM v1 to v2
            # module = "odm_v1_to_v2"
            # module_dir = None
            # input_data_dir = "../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated"
            # input_data_files = None  # ["WWMeasure", "../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated/WWMeasure.csv"]
            # output_dir = "../gen/odm_v1_to_v2"
            # temp_dir = "../gen/odm_v1_to_v2/temp-1000"

            # NWSS to v2
            module = "nwss_reporting_to_v2"
            module_dir = None
            # input_data_dir = "../../../PHES-ODM-Data/nwss/private_renamed_test/"
            input_data_dir = "../../../PHES-ODM-Data/nwss/nwss_renamed/"
            input_data_files = None # [ "nwss", "../../../PHES-ODM-Data/nwss/private_renamed/nwss[cdc-nwss-restricted-data-set-wastewater-2024-03-19].csv" ]
            output_dir = "../gen/nwss_reporting_to_v2"
            temp_dir = "../gen/nwss_reporting_to_v2/temp"

            max_processes = 1
            input_max_rows = 1000
            id_debug = True
        # fmt: on
    else:
        args = argparse.ArgumentParser(
            formatter_class=argparse.ArgumentDefaultsHelpFormatter
        )
        args.add_argument(
            "--module",
            type=str,
            help="The module name for the conversion. Either the 'module' or 'module_dir' command-line arguments must be provided (but not both). A module specifies the source dataset type, the target dataset type, and all required configuration for the conversion.",
            required=False,
        )
        args.add_argument(
            "--module_dir",
            type=str,
            help="The module directory for the conversion. Either the 'module' or 'module_dir' command-line arguments must be provided (but not both). A module specifies the source dataset type, the target dataset type, and all required configuration for the conversion.",
            required=False,
        )
        args.add_argument(
            "--input_data_dir",
            type=str,
            help="Directory containing all of the input data to map. The file names (without extension) correspond to the table name, with anything in square brackets ignored.",
            required=False,
        )
        args.add_argument(
            "--input_data_files",
            nargs="+",
            type=str,
            help="List of all input files and the source class for each file. Format is 'class_name file.csv [class_name2 file2.csv ...]'",
            required=False,
        )
        args.add_argument(
            "--output_dir",
            type=str,
            help="Directory to save all the mapped data to.",
            required=True,
        )
        args.add_argument(
            "--temp_dir",
            type=str,
            help="Directory to save all temporary files to. If specified then the temporary directory is not deleted after processing. If not specified then a system-specified temporary directory is used and deleted after processing. Primarily used for debugging.",
            required=False,
        )
        args.add_argument(
            "--input_max_rows",
            type=int,
            help="The maximum number of rows to map from each input data file. If 0 then map all rows.",
            default=0,
            required=False,
        )
        args.add_argument(
            "--max_processes",
            type=int,
            help="Maximum number of processes to run at a time for mapping the data. If non-positive then the max available processes are used.",
            default=1,
            required=False,
        )
        args.add_argument(
            "--id_debug",
            action="store_true",
            help="If set then run ID generation in debug mode, which only affects what is included in the output data files. Debug data includes some additional columns (eg. original ID values, row number column for linking, primary key index and values, etc.). Debug output will also include any duplicated primary keys, with an additional 'drop' column specifying if it is a duplicate, in which case the row would be dropped when not in debug mode.",
        )
        opts = args.parse_args()

    tic = datetime.now()

    data_files = get_input_data_files(opts.input_data_files, opts.input_data_dir)
    
    mapper = Mapper(
        module=opts.module,
        module_dir=opts.module_dir,        
        id_debug=opts.id_debug,
        multi_bar_progress="get_ipython" not in globals(),
    )
    mapper.full_map(
        data_files=data_files,
        output_dir=opts.output_dir,
        temp_dir=opts.temp_dir,
        input_max_rows=opts.input_max_rows,
        max_processes=opts.max_processes,
    )
