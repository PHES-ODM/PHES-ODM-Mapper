from typing import Annotated

import typer
import yaml
from linkml_runtime import SchemaView

from odm_map.cleaner.clean_data import DataCleaner
from odm_map.utils.cli_utils import get_input_data_files

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    # pretty_exceptions_enable=False,
)

INPUTS_HELP = """List of files and directories to clean. The files
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

OUTPUT_DIR_HELP = """Directory to save all the cleaned data to."""

LOG_FILE_HELP = """The Excel or CSV file to save the log of changes to. For
CSV files, since there may be multiple logs to save, the file name must
have the string '{log_name}' in it. This will be replaced with the name for
each log. For example, for log-file = 'clean_log-{log_name}.csv' and for
the log named 'Unrecognized enum values', the saved CSV file will be named
'clean_log-unrecognized_enum_values.csv'. For Excel files, '{log_name}'
should not be included.
"""

MAX_ROWS_HELP = """The maximum number of rows to clean from each input data
file. If 0 then map all rows."""

CLEAN_OPERATIONS_FILE_HELP = """Optional YAML file specifying the list of clean
operations to perform. If not provided, a default set of operations is used.
See the DataCleaner.clean_data documentation for the expected format."""

DEFAULT_CLEAN_OPERATIONS = [
    {
        "format_and_match_columns": [
            "lowercase",
            {"remove_chars": "-"},
            "alpha_numeric_underscore",
            "single_underscores",
            "trim_trailing_underscores",
        ]
    },
    {
        "add_ontology_ids_to_enums": {
            "match_ontology_id": "\\[[A-Za-z0-9_]+:[A-Za-z0-9_]+\\]$",
        }
    },
    {"correct_enums": True},
    {"check_patterns": True},
]

SCHEMA_HELP = """Schema file that the data conforms to. We will do some basic
cleanup to the data based on this schema (eg. correcting capitalization of
classes and enums). We assume the file name of the file being cleaned is the
class name for the data. If no schema provided then only basic cleanup is
performed"""


@app.command()
def main(
    inputs: Annotated[list[str], typer.Argument(show_default=False, help=INPUTS_HELP)],
    output_dir: Annotated[str, typer.Option(show_default=False, help=OUTPUT_DIR_HELP)],
    log_file: Annotated[str, typer.Option(show_default=False, help=LOG_FILE_HELP)],
    max_rows: Annotated[int, typer.Option(help=MAX_ROWS_HELP)] = 0,
    schema: Annotated[str | None, typer.Option(help=SCHEMA_HELP)] = None,
    clean_operations_file: Annotated[
        str | None, typer.Option(help=CLEAN_OPERATIONS_FILE_HELP)
    ] = None,
):
    if not isinstance(schema, SchemaView) and schema is not None:
        schema = SchemaView(schema)

    if clean_operations_file is not None:
        with open(clean_operations_file, "r") as f:
            clean_operations = yaml.safe_load(f)
    else:
        clean_operations = DEFAULT_CLEAN_OPERATIONS

    data_files = get_input_data_files(inputs, schema=schema)
    cleaner = DataCleaner(schema=schema)
    data_files, _ = cleaner.clean_data(
        data_files=data_files,
        data_frames=None,
        output_dir=output_dir,
        log_file=log_file,
        max_rows=max_rows,
        clean_operations=clean_operations,
    )


if __name__ == "__main__":
    app()
