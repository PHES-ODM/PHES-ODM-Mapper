# %%
from typing import List, Annotated
import typer

from odm_map.mapper.map_data import DataMapper
from odm_map.utils.cli_utils import get_input_data_files
from odm_map.utils.logger import get_logger

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)

logger = get_logger(__name__)

MAIN_HELP = """Apply a list of LinkML-Map mapping schemas to data. The results 
are concatenated and saved to disk."""

INPUTS_HELP = """List of files and directories to map. The files should be
tables of the source dataset. If an input is an Excel file, then all sheets in
the file with a recognized table name in the sheet name are used. If an input
is a CSV, TSV, or TXT file then the file name is used to determine the table
name. When determining a table name, the longest recognized table name in the
source schema that is found in the file name or sheet name is used. To
explicitly specify a table name for a CSV, TSV, or TXT file, precede the file
path with the table name and a colon (eg. 'WWMeasure:data/csv/measures.csv').
When searching for table names (in the file or sheet names), any text after the
first opening square or round bracket is ignored."""

OUTPUT_DIR_HELP = """Directory to save all the mapped data to."""

SOURCE_SCHEMA_HELP = """LinkML schema for the source dataset, that all the
                     input files belong to."""

TARGET_SCHEMA_HELP = """LinkML schema for the target dataset, that all the
                     input files are mapped to."""

MAPPERS_DIR_HELP = """Directory containing all LinkML-Map schemas to use for
                   mapping."""

MAX_ROWS_HELP = """The maximum number of rows to load from each input file. If
                0 then load all rows."""

MAX_PROCESSES_HELP = """Maximum number of processes to use for mapping. For large
                     datasets setting this to a number greater than 1 can improve
                     performance. For small datasets it may degrade performance."""

KEEP_TRACKING_COLUMNS_HELP = """If set then keep the tracking columns in the output.
                             The tracking columns are used for identifying
                             which source data file and row each output row was
                             populated from."""

KEEP_EXTRA_COLUMNS_HELP = """If set then keep the extra columns in the output.
                          The extra columns are additional columns starting with
                          `_extra_` that contain extra information, and are
                          columns that do not exist in the target database."""


@app.command(help=MAIN_HELP)
def main(
    inputs: Annotated[List[str], typer.Argument(show_default=False, help=INPUTS_HELP)],
    output_dir: Annotated[str, typer.Option(show_default=False, help=OUTPUT_DIR_HELP)],
    source_schema: Annotated[
        str, typer.Option(show_default=False, help=SOURCE_SCHEMA_HELP)
    ],
    target_schema: Annotated[
        str, typer.Option(show_default=False, help=TARGET_SCHEMA_HELP)
    ],
    mappers_dir: Annotated[
        str, typer.Option(show_default=False, help=MAPPERS_DIR_HELP)
    ],
    max_rows: Annotated[int, typer.Option(help=MAX_ROWS_HELP)] = 0,
    max_processes: Annotated[int, typer.Option(help=MAX_PROCESSES_HELP)] = 1,
    keep_extra_columns: Annotated[
        bool, typer.Option(help=KEEP_EXTRA_COLUMNS_HELP)
    ] = False,
    keep_tracking_columns: Annotated[
        bool, typer.Option(help=KEEP_TRACKING_COLUMNS_HELP)
    ] = False,
):
    data_files = get_input_data_files(inputs, schema=source_schema)

    mapper = DataMapper()
    mapper.run(
        data_files=data_files,
        data_frames=None,
        output_dir=output_dir,
        source_schema_file=source_schema,
        target_schema_file=target_schema,
        mappers_dir=mappers_dir,
        max_rows=max_rows,
        max_processes=max_processes,
        keep_extra_columns=keep_extra_columns,
        keep_tracking_columns=keep_tracking_columns,
    )


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        opts = {
            # "inputs": ["../../../../PHES-ODM-Data/odm_v1_data/centreau_qc/csv"],
            "inputs": ["/Users/martinwellman/Documents/Health/Wastewater/PHES-ODM-Mapper/PHES-ODM-Mapper/gen/pha4ge-to-v2/temp/cleaned_data"],
            "output_dir": "../../gen/pha4ge-to-v2",
            "source_schema": "../data/modules/pha4ge-to-v2/schemas/pha4ge.yaml",
            "target_schema": "../data/modules/_shared/schemas/odm_v2.yaml",
            "mappers_dir": "../data/modules/pha4ge-to-v2/mappers",
            "max_rows": 100,
            "max_processes": 1,
            "keep_extra_columns": True,
            "keep_tracking_columns": True,
        }
        # fmt: on
        main(**opts)
    else:
        app()
