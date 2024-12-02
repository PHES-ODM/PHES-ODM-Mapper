# %%
from typing import List
import typer

from linkml_runtime import SchemaView

from odm_map.cleaner.clean_data import DataCleaner
from odm_map.utils.cli_utils import get_input_data_files

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    # pretty_exceptions_enable=False,
)

INPUT_DIR_HELP = """Directory containing all of the input data files to clean.
                 The table the file belongs to is determined by the file name:
                 after ignoring the file extension and anything after the first
                 opening square or round bracket, the longest table name (in
                 the source dataset) that is found in the file name will be
                 used. (eg. '1-WWMeasure[2024-11-09].csv' is a valid file name
                 for the table 'WWMeasure'). If an Excel file is found, then
                 the sheet tab names will be used to match the table name.
                 Sheets that do not match a table name will be ignored."""

INPUT_FILE_HELP = """Input data file to clean. Multiple --input-file
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

OUTPUT_DIR_HELP = """Directory to save all the cleaned data to."""

MAX_ROWS_HELP = """The maximum number of rows to clean from each input data
                file. If 0 then map all rows."""

SCHEMA_HELP = """Schema file that the data conforms to. We will do some basic
              cleanup to the data based on this schema (eg. correcting
              capitalization of classes and enums). We assume the file name of
              the file being cleaned is the class name for the data. If no
              schema provided then only basic cleanup is performed"""


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
    max_rows: int = typer.Option(
        default=0,
        help=MAX_ROWS_HELP,
    ),
    schema: str = typer.Option(
        default=None,
        help=SCHEMA_HELP,
    ),
):
    if not isinstance(schema, SchemaView) and schema is not None:
        schema = SchemaView(schema)

    data_files = get_input_data_files(input_file, input_dir, schema=schema)
    cleaner = DataCleaner(schema=schema)
    data_files, _ = cleaner.clean_data(
        data_files=data_files,
        data_frames=None,
        output_dir=output_dir,
        max_rows=max_rows,
    )


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        opts = {
            # "input_dir": "../../../../../PHES-ODM-Data/odm_v1_data/centreau_qc/updated copy",
            # # "input_dir": "/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Data/odm_v1_data/joakim/excel/",
            # "input_file": None,
            # "output_dir": "../../../gen/odm-v1-to-v2-test/cleaned_data",
            # "max_rows": 100,
            # "schema": "../data/modules/odm-v1-to-v2/schemas/odm_v1.yaml",

            # "input_dir": "../../../../../PHES-ODM-Data/nwss/nwss_renamed/",
            "input_dir": "../../../gen/nwss-reporting-to-v2-test/mapped_data_ids",
            # "input_dir": None,
            "input_file": None,
            "output_dir": "../../../gen/nwss-reporting-to-v2-test/cleaned_data-final",
            "max_rows": None, #100,
            # "schema": "../data/modules/nwss-reporting-to-v2/schemas/nwss_reporting.yaml",
            "schema": "../data/modules/nwss-reporting-to-v2/schemas/odm_v2.yaml",
        }
        # fmt: on
        main(**opts)
    else:
        app()
