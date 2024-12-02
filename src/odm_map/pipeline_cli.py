# %%
"""
# Command-Line

To run the pipeline to map data from the command-line, execute the following for ODM v1 to 
ODM v2 (replacing values where appropriate):

```console
cd src
python3 pipeline_cli.py \
    --module odm-v1-to-v2 \
    --input-dir "path/to/input/data" \
    --output-dir "../gen/odm-v1-to-v2"
```
"""

from typing import List
from datetime import datetime
import sys
import typer
from click.exceptions import UsageError

from odm_map.utils.modules import get_all_modules
from odm_map.utils.logger import get_logger
from odm_map.utils.clean_exit_error import CleanExitError

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    # pretty_exceptions_enable=False,
)

logger = get_logger(__name__)

# Make a string showing all available module names
_module_names = [f"'{m}'" for m in get_all_modules()]
_module_names = ", ".join(_module_names)
if not _module_names:
    _module_names = "<No modules available>"


MODULE_HELP = f"""The installed module name for the conversion. Allowable
               values: {_module_names}. Either the --module or --module-dir
               command-line arguments must be provided (but not both). A module
               specifies the source dataset type, the target dataset type, and
               all required configuration for the conversion."""

MODULE_DIR_HELP = """The module directory for the conversion. Either the
                  --module or --module-dir command-line arguments must be
                  provided (but not both). A module specifies the source
                  dataset type, the target dataset type, and all required
                  configuration for the conversion."""

INPUT_DIR_HELP = """Directory containing all of the input data files to map.
                 The table the file belongs to is determined by the file name:
                 after ignoring the file extension and anything after the first
                 opening square or round bracket, the longest table name (in
                 the source dataset) that is found in the file name will be
                 used. (eg. '1-WWMeasure[2024-11-09].csv' is a valid file name
                 for the table 'WWMeasure'). If an Excel file is found, then
                 the sheet tab names will be used to match the table name.
                 Sheets that do not match a table name will be ignored."""

INPUT_FILE_HELP = """Input data file to map. Multiple --input-file options can
                  be specified. The table the file belongs to is determined by
                  the file name: after ignoring the file extension and anything
                  after the first opening square or round bracket, the longest
                  table name (in the source dataset) that is found in the file
                  name will be used. (eg. '1-WWMeasure[2024-11-09].csv' is a
                  valid file name for the table 'WWMeasure'). If an Excel file
                  is found, then the sheet tab names will be used to match the
                  table name. Sheets that do not match a table name will be
                  ignored. To override this behavior for non-Excel files,
                  precede the file path with the table name and a colon, eg.
                  'WWMeasure:data/measures.csv'. Place the full string in
                  quotes if the path contains any spaces."""

OUTPUT_DIR_HELP = """Directory to save all the mapped data to."""

TEMP_DIR_HELP = """Directory to save all temporary files to. If specified then
                the temporary directory is not deleted after processing. If not
                specified then a system-specified temporary directory is used
                and deleted after processing. Primarily used for debugging."""

MAX_ROWS_HELP = """The maximum number of rows to map from each input data file.
                If 0 then map all rows."""

MAX_PROCESSES_HELP = """Maximum number of processes to run at a time for
                     mapping the data. If non-positive then the max available
                     processes are used."""

DEBUG_HELP = """If set then run ID generation in debug mode, which only affects
             what is included in the output data files. Debug data
             includes some additional columns (eg. original ID values, row
             number column for linking, primary key index and values,
             etc.). Debug output will also include any duplicated primary
             keys, with an additional 'drop' column specifying if it is a
             duplicate, in which case the row would be dropped when not in
             debug mode."""


@app.command()
def main(
    module: str = typer.Option(
        default=None,
        help=MODULE_HELP,
    ),
    module_dir: str = typer.Option(
        default=None,
        help=MODULE_DIR_HELP,
    ),
    input_dir: str = typer.Option(
        default=None,
        help=INPUT_DIR_HELP,
    ),
    input_file: List[str] = typer.Option(
        default=[],
        help=INPUT_FILE_HELP,
    ),
    output_dir: str = typer.Option(
        default=...,
        help=OUTPUT_DIR_HELP,
    ),
    temp_dir: str = typer.Option(
        default=None,
        help=TEMP_DIR_HELP,
    ),
    max_rows: int = typer.Option(
        default=0,
        help=MAX_ROWS_HELP,
    ),
    max_processes: int = typer.Option(
        default=1,
        help=MAX_PROCESSES_HELP,
    ),
    debug: bool = typer.Option(
        default=False,
        help=DEBUG_HELP,
    ),
):
    try:
        # Do some checks on the CLI options
        if not module and not module_dir:
            raise UsageError("Either '--module' or '--module-dir' must be specified.")
        if module and module_dir:
            raise UsageError(
                "Only one of '--module' or '--module-dir' can be specified."
            )
        if not input_dir and not input_file:
            raise UsageError(
                "At least one or more of '--input-dir' or '--input-file' must be specified."
            )
        if module and module not in get_all_modules(include_titles=False):
            raise UsageError(
                f"Invalid value for '--module': '{module}' is not one of {_module_names}"
            )

        logger.info(f"Starting run at {datetime.now()}")

        # These imports are placed here entirely for performance reasons. The imports can
        # take some time, so we make sure all error checking is done first. It will also
        # avoid these imports when the user runs with the --help cli flag.
        from odm_map.pipeline import Pipeline
        from odm_map.utils.modules import get_source_schema
        from odm_map.utils.cli_utils import get_input_data_files

        source_schema = get_source_schema(module, module_dir)
        data_files = get_input_data_files(input_file, input_dir, schema=source_schema)

        pipeline = Pipeline(
            module=module,
            module_dir=module_dir,
        )
        pipeline.run(
            data_files=data_files,
            output_dir=output_dir,
            temp_dir=temp_dir,
            max_rows=max_rows,
            max_processes=max_processes,
            multi_bar_progress="get_ipython" not in globals(),
            debug_mode=debug,
        )
    except CleanExitError as e:
        logger.error(str(e))
        if "get_ipython" not in globals():
            sys.exit(1)
    except KeyboardInterrupt:
        logger.error("Interrupted by user")
        if "get_ipython" not in globals():
            sys.exit(1)


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        opts = {
            # ODM v1 to v2,
            "module": "odm-v1-to-v2",
            "module_dir": None,
            # "input_dir": "../../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated",
            "input_dir": "../../../../PHES-ODM-Data/odm_v1_data/excel/excel",
            # "input_dir": "/Users/martinwellman/Documents/Health/Wastewater/sars-cov-2-data/CSV/Ottawa",
            # "input_dir": None,
            # "input_file": ["wwmeasure/samplewwmeasure.csv", "Sample:../../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated/Sample.csv"],
            "input_file": None,
            "output_dir": "../../gen/odm-v1-to-v2-test-new",
            "temp_dir": None, #"../../gen/odm-v1-to-v2-test-excel/temp",

            # NWSS to v2,
            # "module": "nwss-reporting-to-v2",
            # "module_dir": None,
            # # "input_dir": "../../../../PHES-ODM-Data/nwss/private_renamed_test/",
            # "input_dir": "../../../../PHES-ODM-Data/nwss/nwss_renamed/",
            # # "input_dir": "../../../../PHES-ODM-Data/nwss/nwss_renamed_excel/",
            # # "input_dir": "/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Data/nwss/nwss_renamed_excel",
            # "input_files": None, # [ "nwss", "../../../../PHES-ODM-Data/nwss/private_renamed/nwss[cdc-nwss-restricted-data-set-wastewater-2024-03-19].csv" ],
            # "output_dir": "../../gen/nwss-reporting-to-v2-xl2",
            # "temp_dir": "../../gen/nwss-reporting-to-v2-xl2/temp",

            "max_processes": 1,
            "max_rows": 100,
            "debug": True,
        }
        # fmt: on
        main(**opts)
    else:
        app()
