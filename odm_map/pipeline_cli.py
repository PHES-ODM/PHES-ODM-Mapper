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

from typing import List, Annotated
from datetime import datetime
import typer
from click.exceptions import UsageError, ClickException

from odm_map.utils.modules import get_all_modules
from odm_map.utils.logger import get_logger, make_logger_bullet_list
from odm_map.utils.clean_exit_error import CleanExitError

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    # pretty_exceptions_enable=False,
    rich_markup_mode="rich",
)

logger = get_logger(__name__)

# Make a string showing all available module names
_module_names = [f"'{m}'" for m in get_all_modules()]
_module_names = ", ".join(_module_names)
if not _module_names:
    _module_names = "<No modules available>"

# Make a Markdown string to show a list of all modules
_module_list = get_all_modules(include_titles=True)
_module_list = make_logger_bullet_list(_module_list, bullet="- ", indent=4)
if not _module_list:
    _module_list = "<No modules available>"

MAIN_HELP = f"""Map between various wastewater surveillance database formats.

The following modules are installed:
[bold][/bold]
{_module_list}
"""

INPUTS_HELP = """List of files and directories to map. The files should be
tables from the source dataset. For Excel files, the sheet tab names will be
used to determine which table in the source dataset the sheet belongs to. For
all other files, the file name will be used to determine which table the file
belongs to. In order to determine the table name based on the sheet or file
name, both the extension and any text after the first opening square or round
bracket are ignored. After this, the longest matching table name (in the source
dataset) that is found in the file name or sheet name is used. For example, a
file named "1. WWMeasure[2024-12-20].csv" will be a valid file name for the
table "WWMeasure". If no match is found then the file or sheet is ignored."""


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


@app.command(help=MAIN_HELP)
def main(
    inputs: Annotated[List[str], typer.Argument(show_default=False, help=INPUTS_HELP)],
    module: str = typer.Option(
        default=None,
        help=MODULE_HELP,
    ),
    module_dir: str = typer.Option(
        default=None,
        help=MODULE_DIR_HELP,
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
        if module and module not in get_all_modules(include_titles=False):
            raise UsageError(
                f"Invalid value for '--module': '{module}' is not one of {_module_names}"
            )

        logger.info(f"Starting run at {datetime.now()}")

        # These imports are placed here entirely for performance reasons. The imports can
        # take some time, so we make sure all cli error checking is done first. It will also
        # avoid these imports when the user runs with the --help cli flag.
        from linkml_runtime import SchemaView
        from odm_map.pipeline import Pipeline
        from odm_map.utils.modules import get_source_schema
        from odm_map.utils.cli_utils import get_input_data_files
        from odm_map.utils.schema_utils import all_classes_without_tree_root

        source_schema = get_source_schema(module, module_dir)
        if source_schema and not isinstance(source_schema, SchemaView):
            source_schema = SchemaView(source_schema)

        data_files = get_input_data_files(inputs, schema=source_schema)

        # Report error if no data_files found
        if not data_files:
            all_classes = all_classes_without_tree_root(source_schema)
            all_classes = ", ".join(all_classes)
            raise CleanExitError(
                f"No input files found for source dataset {source_schema.schema.name}. Recognized tables are: {all_classes}"
            )

        # Run the Pipeline (ie. do the full mapping)
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
        print("", end="\r")
        raise ClickException(str(e))
    except KeyboardInterrupt:
        print("", end="\r")
        raise ClickException("Interrupted by user")


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        opts = {
            # ODM v1 to v2,
            # # "inputs": ["../../../PHES-ODM-Data/odm_v1_data/excel/excel"],
            # "inputs": ["../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated/"],
            # # "inputs": ["a.xlsx"],
            # "module": "odm-v1-to-v2",
            # "module_dir": None,
            # # "inputs": ["../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated"],
            # # "inputs": ["../../../PHES-ODM-Data/odm_v1_data/excel/excel"],
            # # "inputs": ["/Users/martinwellman/Documents/Health/Wastewater/sars-cov-2-data/CSV/Ottawa"],
            # "output_dir": "../gen/odm-v1-to-v2-test-new",
            # "temp_dir": None, #"../gen/odm-v1-to-v2-test-excel/temp",

            # NWSS to v2,
            "module": "nwss-reporting-to-v2",
            "module_dir": None,
            # "inputs": ["../../../PHES-ODM-Data/nwss/private_renamed_test/"],
            # "inputs": ["../../../PHES-ODM-Data/nwss/nwss_renamed/"],
            # "inputs": ["../../../PHES-ODM-Data/nwss/nwss_renamed/nwss[cdc-nwss-restricted-dataset-wastewater-20240730].csv"],
            "inputs": ["../../../PHES-ODM-Data/nwss/test_mathew/"],
            # "inputs": ["../../../PHES-ODM-Data/nwss/nwss_renamed_excel/"],
            # "inputs": ["/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Data/nwss/nwss_renamed_excel"],
            "output_dir": "../gen/nwss-reporting-to-v2-xl2",
            "temp_dir": "../gen/nwss-reporting-to-v2-xl2/temp",

            "max_processes": 1,
            "max_rows": 1000,
            "debug": True,
        }
        # fmt: on
        main(**opts)
    else:
        app()
