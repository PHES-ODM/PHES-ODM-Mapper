# %%
from typing import List, Annotated
import typer

from odm_map.filter.filter_data import DataFilter
from odm_map.utils.cli_utils import get_input_data_files

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    # pretty_exceptions_enable=False,
)

INPUTS_HELP = """List of files and directories to filter. The files
should be tables of the dataset specified by '--schema'. If an input is an
Excel file, then all sheets in the file with a recognized table name in the
sheet name are used. If an input is a CSV, TSV, or TXT file then the file name
is used to determine the table name. When determining a table name, the longest
recognized table name in the schema that is found in the file name or sheet
name is used. To explicitly specify a table name for a CSV, TSV, or TXT file,
precede the file path with the table name and a colon (eg.
'WWMeasure:data/csv/measures.csv'). When searching for table names (in the file
or sheet names), any text after the first opening square or round bracket is
ignored."""

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
    inputs: Annotated[List[str], typer.Argument(show_default=False, help=INPUTS_HELP)],
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
    data_files = get_input_data_files(inputs, schema=schema)
    filterer = DataFilter(filter_config_file)
    filterer.run_filter(
        data_files=data_files,
        output_dir=output_dir,
    )


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        opts = {
            # "inputs": ["../../gen/nwss-reporting-to-v2/temp/mapped_data"],
            "inputs": ["/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Data/odm_v2_data/mapped_from_nwss"],
            "filter_config_file": "../data/modules/nwss-reporting-to-v2/filters/nwss_reporting_to_v2_filters.xlsx",
            "output_dir": "../../gen/nwss-reporting-to-v2-test/filtered_mapped_data",
            "schema": "../data/modules/odm-v1-to-v2/schemas/odm_v2.yaml",
        }
        # fmt: on
        main(**opts)
    else:
        app()
