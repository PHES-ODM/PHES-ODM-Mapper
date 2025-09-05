from typing import List, Annotated
import typer

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

MAX_ROWS_HELP = """The maximum number of rows to clean from each input data
file. If 0 then map all rows."""

SCHEMA_HELP = """Schema file that the data conforms to. We will do some basic
cleanup to the data based on this schema (eg. correcting capitalization of
classes and enums). We assume the file name of the file being cleaned is the
class name for the data. If no schema provided then only basic cleanup is
performed"""


@app.command()
def main(
    inputs: Annotated[List[str], typer.Argument(show_default=False, help=INPUTS_HELP)],
    output_dir: Annotated[str, typer.Option(show_default=False, help=OUTPUT_DIR_HELP)],
    max_rows: Annotated[int, typer.Option(help=MAX_ROWS_HELP)] = 0,
    schema: Annotated[str, typer.Option(help=SCHEMA_HELP)] = None,
):
    if not isinstance(schema, SchemaView) and schema is not None:
        schema = SchemaView(schema)

    data_files = get_input_data_files(inputs, schema=schema)
    cleaner = DataCleaner(schema=schema)
    data_files, _ = cleaner.clean_data(
        data_files=data_files,
        data_frames=None,
        output_dir=output_dir,
        max_rows=max_rows,
        # @TODO: Do not hardcode these!
        clean_operations=[
            {
                "format_columns": [
                    "lowercase",
                    {"remove_chars": "-"},
                    "alpha_numeric_underscore",
                    "single_underscores",
                    "trim_trailing_underscores",
                ]
            },
            {
                "add_ontology_ids_to_enums": {
                    "match_ontology_id": r"\[[A-Za-z0-9_]+:[A-Za-z0-9_]+\]$",
                }
            },
            {"correct_enums": True},
            {"report_unknown_enum_values": True},
            {"remove_unknown_columns": True},
        ],
    )


if __name__ == "__main__":
    app()
