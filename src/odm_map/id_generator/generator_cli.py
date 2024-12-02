# %%
from typing import List
import typer

from odm_map.id_generator.generator import IDGenerator
from odm_map.id_generator.generator_data import DROP_COLUMN
from odm_map.utils.cli_utils import get_input_data_files

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    # pretty_exceptions_enable=False,
)

INPUT_DIR_HELP = """Directory containing all of the input data files to
                 generate IDs for. The table the file belongs to is determined
                 by the file name: after ignoring the file extension and
                 anything after the first opening square or round bracket, the
                 longest table name (in the source dataset) that is found in
                 the file name will be used. (eg. '1-WWMeasure[2024-11-09].csv'
                 is a valid file name for the table 'WWMeasure'). If an Excel
                 file is found, then the sheet tab names will be used to match
                 the table name. Sheets that do not match a table name will be
                 ignored."""

INPUT_FILE_HELP = """Input data file to generate IDs for. Multiple --input-file
                  options can be specified. The table the file belongs to is
                  determined by the file name: after ignoring the file
                  extension and anything after the first opening square or
                  round bracket, the longest table name (in the source dataset)
                  that is found in the file name will be used. (eg.
                  '1-WWMeasure[2024-11-09].csv' is a valid file name for the
                  table 'WWMeasure'). If an Excel file is found, then the sheet
                  tab names will be used to match the table name. Sheets that
                  do not match a table name will be ignored. To override this
                  behavior for non-Excel files, precede the file path with the
                  table name and a colon, eg. 'WWMeasure:data/measures.csv'.
                  Place the full string in quotes if the path contains any
                  spaces."""

CONFIG_FILE_HELP = """The YAML config file."""

ID_CODE_FILE_HELP = """The XLSX, CSV, TSV, TXT, YAML, or YML configuration file
                    that contains the ID generation code. If an XLSX file then
                    the sheet named by --id-code-sheet is loaded."""

ID_CODE_SHEET_HELP = """If --id-code-file is an Excel file, then load the code
                     from the sheet with this name."""

OUTPUT_DIR_HELP = """Directory to save the final data to, in which all IDs have
                  been generated."""

SCHEMA_HELP = """Schema file that the data conforms to. This will only be used
              to determine which table each input file belongs to. If not
              specified then the file name (or sheet name for Excel files) will
              be treated as the table name, ignoring the extension and anything
              after the first square or round bracket."""

DEBUG_HELP = f"""If set then run in debug mode, which only affects what is
             included in the output data files. Debug data includes some
             additional columns (eg. original ID values, row number column for
             linking, primary key index and values, etc.). Debug output will
             also include any duplicated primary keys, with an additional
             '{DROP_COLUMN}' column specifying if it is a duplicate, in which
             case the row would be dropped when not in debug mode."""


@app.command()
def main(
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
    config_file: str = typer.Option(
        default=...,
        help=CONFIG_FILE_HELP,
    ),
    id_code_file: str = typer.Option(
        default=...,
        help=ID_CODE_FILE_HELP,
    ),
    id_code_sheet: str = typer.Option(
        default=None,
        help=ID_CODE_SHEET_HELP,
    ),
    schema: str = typer.Option(
        default=None,
        help=SCHEMA_HELP,
    ),
    debug: bool = typer.Option(
        default=False,
        help=DEBUG_HELP,
    ),
):
    data_files = get_input_data_files(input_file, input_dir, schema=schema)

    gen = IDGenerator(
        data_files=data_files,
        data_frames=None,
        config_file=config_file,
        id_code_file=id_code_file,
        id_code_sheet=id_code_sheet,
        multi_bar_progress="get_ipython" not in globals(),
    )
    gen.run_generator(
        keep_tracking_columns=debug,
        keep_debug_columns=debug,
        remove_duplicates=not debug,
    )
    _ = gen.save_all(output_dir)


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        opts = {
            # Test
            # "input_dir": "../../../gen/test/source_data",
            # "input_file": None,
            # "output_dir": "../../../gen/test/mapped_data_ids",
            # "id_code_file": "../data/modules/test/ids.xlsx",
            # "id_code_sheet": "id_code",
            # "config_file": "../data/modules/test/ids.yaml",
            
            # NWSS to ODM v2
            # "input_dir": "../../../gen/nwss-reporting-to-v2/temp-1000/mapped_data",
            # "input_dir": "/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Data/odm_v2_data/mapped_from_nwss",
            "input_dir": "/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Data/nwss/nwss_preid_excel",
            "input_file": None,
            "output_dir": "../../../gen/nwss-reporting-to-v2-test/mapped_data_ids",
            "id_code_file": "../data/modules/nwss-reporting-to-v2/ids/nwss_reporting_to_v2_id_code.xlsx",
            "id_code_sheet": "id_code",
            "config_file": "../data/modules/nwss-reporting-to-v2/ids/nwss_reporting_to_v2_id_config.yaml",
            "schema": "../data/modules/nwss-reporting-to-v2/schemas/odm_v2.yaml",

            # ODM v1 to ODM v2,
            # "input_dir": "../../../gen/odm-v1-to-v2/temp/mapped_data",
            # "input_file": None,
            # "output_dir": "../../../gen/odm-v1-to-v2/mapped_data_ids",
            # "id_code_file": "../data/modules/odm-v1-to-v2/ids/odm_v1_to_v2_id_code.xlsx",
            # "id_code_sheet": "id_code",
            # "config_file": "../data/modules/odm-v1-to-v2/ids/odm_v1_to_v2_id_config.yaml",
            # "schema": "../data/modules/odm-v1-to-v2/schemas/odm_v2.yaml",

            "debug": True,
        }
        # fmt: on
        main(**opts)
    else:
        app()
