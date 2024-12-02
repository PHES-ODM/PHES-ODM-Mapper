# %%
from typing import List
import typer

from odm_map.filter.filter_data import DataFilter
from odm_map.utils.cli_utils import get_input_data_files

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    # pretty_exceptions_enable=False,
)

INPUT_DIR_HELP = """Filter all xlsx, csv, txt, and tsv files in this directory.
                 txt files are treated as tab-separated."""

INPUT_FILE_HELP = """Input data file to filter. Multiple --input-file options
                  can be specified. The table the file belongs to is determined
                  by the file name: the longest table name (in the source
                  dataset) that is found in the file name will be used. (eg.
                  '1-WWMeasure[2024-11-09].csv' is a valid file name for the
                  table 'WWMeasure'). If an Excel file is found, then the sheet
                  tab names will be used to match the table name. Sheets that
                  do not match a table name will be ignored. To override this
                  behavior for non-Excel files, precede the file path with the
                  table name and a colon, eg. 'WWMeasure:data/measures.csv'.
                  Place the full string in quotes if the path contains any
                  spaces."""

FILTER_CONFIG_FILE_HELP = """Location of the CSV or TSV filtering configuration
                          file."""

OUTPUT_DIR_HELP = """Directory to save all the filtered data to."""

SCHEMA_HELP = """Schema file that the data conforms to. This will only be used
              to determine which table each input file belongs to. If not
              specified then the file name (or sheet name for Excel files) will
              be treated as the table name, ignoring the extension and anything
              after the first square or round bracket."""


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
    filter_config_file: str = typer.Option(
        default=...,
        help=FILTER_CONFIG_FILE_HELP,
    ),
    output_dir: str = typer.Option(
        default=...,
        help=OUTPUT_DIR_HELP,
    ),
    schema: str = typer.Option(
        default=None,
        help=SCHEMA_HELP,
    ),
):
    data_files = get_input_data_files(input_file, input_dir, schema=schema)
    filterer = DataFilter(filter_config_file)
    filterer.run_filter(
        data_files=data_files,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        opts = {
            # "input_dir": "../../gen/nwss-reporting-to-v2/temp/mapped_data",
            "input_dir": "/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Data/odm_v2_data/mapped_from_nwss",
            "input_file": None,
            "filter_config_file": "../data/modules/nwss-reporting-to-v2/filters/nwss_reporting_to_v2_filters.xlsx",
            "output_dir": "../../gen/nwss-reporting-to-v2-test/filtered_mapped_data",
            "schema": "../data/modules/odm-v1-to-v2/schemas/odm_v2.yaml",
        }
        # fmt: on
        main(**opts)
    else:
        app()
