from typing import List, Annotated
import typer

from odm_map.id_generator.generator import IDGenerator
from odm_map.id_generator.generator_data import DROP_COLUMN
from odm_map.utils.cli_utils import get_input_data_files

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)

MAIN_HELP = """Generate IDs for DataFrames."""

INPUTS_HELP = """List of files and directories to generate IDs for. The files
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

CONFIG_FILE_HELP = """The YAML config files. If multiple files are specified
then they are merged together."""

ID_CODE_FILES_HELP = """The XLSX, CSV, TSV, TXT, YAML, or YML configuration
files that contains the ID generation code. If an XLSX file then the sheet
named by --id-code-sheet, at the same index, is loaded."""

ID_CODE_SHEETS_HELP = """If --id-code-file at the same index is an Excel file,
then load the code from the sheet with this name."""

OUTPUT_DIR_HELP = """Directory to save the final data to, in which all IDs have
been generated."""

SCHEMA_HELP = """Schema file that the data conforms to. This will only be used
to determine which table each input file belongs to. If not specified then the
file name (or sheet name for Excel files) will be treated as the table name,
ignoring the extension and anything after the first square or round bracket."""

DEBUG_HELP = f"""If set then run in debug mode, which only affects what is
included in the output data files. Debug data includes some additional columns
(eg. original ID values, row number column for linking, primary key index and
values, etc.). Debug output will also include any duplicated primary keys, with
an additional '{DROP_COLUMN}' column specifying if it is a duplicate, in which
case the row would be dropped when not in debug mode."""


@app.command(help=MAIN_HELP)
def main(
    inputs: Annotated[List[str], typer.Argument(show_default=False, help=INPUTS_HELP)],
    output_dir: Annotated[str, typer.Option(show_default=False, help=OUTPUT_DIR_HELP)],
    config_file: Annotated[
        List[str], typer.Option(show_default=False, help=CONFIG_FILE_HELP)
    ],
    id_code_files: Annotated[
        List[str], typer.Option(show_default=False, help=ID_CODE_FILES_HELP)
    ],
    id_code_sheets: Annotated[List[str], typer.Option(help=ID_CODE_SHEETS_HELP)] = None,
    schema: Annotated[str, typer.Option(help=SCHEMA_HELP)] = None,
    debug: Annotated[bool, typer.Option(help=DEBUG_HELP)] = False,
):
    data_files = get_input_data_files(inputs, schema=schema)

    new_code_files = []
    if not id_code_sheets:
        id_code_sheets = len(id_code_files) * [None]
    else:
        id_code_sheets = id_code_sheets + [None] * (
            len(id_code_files) - len(id_code_sheets)
        )
    for id_code_file, id_code_sheet in zip(id_code_files, id_code_sheets):
        new_code_files.append(
            {"id_code_file": id_code_file, "id_code_sheet": id_code_sheet}
        )
    id_code_files = new_code_files

    gen = IDGenerator(
        data_files=data_files,
        data_frames=None,
        schema=schema,
        config_file=config_file,
        id_code_files=id_code_files,
        multi_bar_progress="get_ipython" not in globals(),
    )
    gen.run_generator(
        keep_extra_columns=debug,
        keep_tracking_columns=debug,
        keep_debug_columns=debug,
        remove_duplicates=not debug,
    )
    _ = gen.save_all(output_dir)


if __name__ == "__main__":
    app()
