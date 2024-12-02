# %%
from typing import List
import typer
from click.exceptions import UsageError

from odm_map.mapper.map_data import DataMapper
from odm_map.utils.cli_utils import get_input_data_files
from odm_map.utils.logger import get_logger

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    # pretty_exceptions_enable=False,
)

logger = get_logger(__name__)

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

KEEP_TRACKING_COLUMNS_HELP = """If set keep the tracking columns in the output.
                             The tracking columns are used for identifying
                             which source data file and row each output row was
                             populated from."""


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
    source_schema: str = typer.Option(
        default=...,
        help=SOURCE_SCHEMA_HELP,
    ),
    target_schema: str = typer.Option(
        default=...,
        help=TARGET_SCHEMA_HELP,
    ),
    mappers_dir: str = typer.Option(
        default=...,
        help=MAPPERS_DIR_HELP,
    ),
    max_rows: int = typer.Option(
        default=0,
        help=MAX_ROWS_HELP,
    ),
    max_processes: int = typer.Option(
        default=1,
        help=MAX_PROCESSES_HELP,
    ),
    keep_tracking_columns: bool = typer.Option(
        default=False,
        help=KEEP_TRACKING_COLUMNS_HELP,
    ),
):
    if not input_dir and not input_file:
        raise UsageError(
            "At least one or more of '--input-dir' or '--input-file' must be specified."
        )

    data_files = get_input_data_files(input_file, input_dir, schema=source_schema)

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
        keep_tracking_columns=keep_tracking_columns,
        # prepare_barid=prepare_barid,
        # map_barid=map_barid,
        # convert_barid=convert_barid,
    )


if __name__ == "__main__":
    if "get_ipython" in globals():
        # fmt: off
        opts = {
            "input_dir": "../../../../PHES-ODM-Data/odm_v1_data/centreau_qc/csv",
            "input_file": [],
            "output_dir": "../../gen/odm-v1-to-v2-test",
            "source_schema": "../data/modules/odm-v1-to-v2/schemas/odm_v1.yaml",
            "target_schema": "../data/modules/odm-v1-to-v2/schemas/odm_v2.yaml",
            "mappers_dir": "../data/modules/odm-v1-to-v2/mappers",
            "max_rows": 50,
            "max_processes": 1,
            "keep_tracking_columns": False,
        }
        # fmt: on
        main(**opts)
    else:
        app()
