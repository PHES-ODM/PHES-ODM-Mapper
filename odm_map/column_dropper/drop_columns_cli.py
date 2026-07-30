from pathlib import Path
from typing import Annotated

import typer

from odm_map.column_dropper.drop_columns import DropColumns
from odm_map.utils.cli_utils import get_input_data_files

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)

MAIN_HELP = """Drop columns from tabular data. The dropped columns
can be configured from the command line. Options include dropping extra columns
(columns starting with _extra_), dropping tracking columns (columns that
specify which row and file/table the row was populated from), and dropping
columns that are not part of the class according to a LinkML schema."""

INPUTS_HELP = """All the data files to drop columns from. The class the data
file belongs to is determined by the file's name. eg. measures.csv belongs to
the measures class, and samples[2025-07-01].csv belongs to the samples
class."""

DROP_EXTRA_COLUMNS_HELP = """If set then drop the extra columns. These are
columns that begin with the string '_extra_'."""

DROP_TRACKING_COLUMNS_HELP = """If set then drop the tracking columns.
These are columns that specify from which row number and class/table the
current row was populated from during a mapping operation."""

KEEP_COLUMNS_IN_SCHEMA_ONLY_HELP = """If set then only keep the columns that
are recognized for the class according to the schema specified by the --schema
option."""

OUTPUT_DIR_HELP = """Directory to save the results to."""

SCHEMA_HELP = """If --keep-columns-in-schema-only is specified, then this is
the LinkML schema used to determine which columns to keep. If
--keep-columns-in-schema-only is not specified then --schema is not
required."""

MAX_ROWS_HELP = """Maximum number of rows to load from each input data file.
If not set or 0 then all rows are loaded."""


@app.command(help=MAIN_HELP)
def main(
    inputs: Annotated[list[Path], typer.Argument(show_default=False, help=INPUTS_HELP)],
    output_dir: Annotated[Path, typer.Option(show_default=False, help=OUTPUT_DIR_HELP)],
    drop_extra_columns: Annotated[
        bool, typer.Option(help=DROP_EXTRA_COLUMNS_HELP)
    ] = False,
    drop_tracking_columns: Annotated[
        bool, typer.Option(help=DROP_TRACKING_COLUMNS_HELP)
    ] = False,
    keep_columns_in_schema_only: Annotated[
        bool, typer.Option(help=KEEP_COLUMNS_IN_SCHEMA_ONLY_HELP)
    ] = False,
    schema: Annotated[Path | None, typer.Option(help=SCHEMA_HELP)] = None,
    max_rows: Annotated[int | None, typer.Option(help=MAX_ROWS_HELP)] = None,
):
    data_files = get_input_data_files(inputs, schema=schema)

    drop = DropColumns()
    drop.drop_columns(
        data_files=data_files,
        data_frames=None,
        drop_extra_columns=drop_extra_columns,
        drop_tracking_columns=drop_tracking_columns,
        keep_columns_in_schema_only=keep_columns_in_schema_only,
        output_dir=output_dir,
        max_rows=max_rows,
        schema=schema,
    )


if __name__ == "__main__":
    app()
