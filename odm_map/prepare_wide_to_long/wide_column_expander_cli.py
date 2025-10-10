from typing import Annotated, List
from pathlib import Path
import typer

from odm_map.prepare_wide_to_long.wide_column_expander import WideColumnExpander

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)

MAIN_HELP = """Expand ODM wide column names into separate columns for each
value specified in the column name."""

INPUTS_HELP = """Path to files to use as inputs to the wide column expander."""

CONFIG_HELP = """Configuration file for the expander."""

TARGET_SCHEMA_HELP = """Path to the LinkML schema that the data is for."""

OUTPUT_FILE_HELP = """If specified, then the file to save the expanded data to."""

SOURCE_CLASS_HELP = """The name of the source class in the mapping."""


@app.command(help=MAIN_HELP)
def main(
    inputs: Annotated[List[Path], typer.Argument(show_default=False, help=INPUTS_HELP)],
    config: Annotated[Path, typer.Option(show_default=False, help=CONFIG_HELP)],
    target_schema: Annotated[
        Path, typer.Option(show_default=False, help=TARGET_SCHEMA_HELP)
    ],
    source_class: Annotated[
        str, typer.Option(show_default=False, help=SOURCE_CLASS_HELP)
    ],
    output_file: Annotated[
        Path, typer.Option(show_default=False, help=OUTPUT_FILE_HELP)
    ] = None,
):
    expander = WideColumnExpander(
        config=config, source_class_name=source_class, target_schema=target_schema
    )
    df = expander.expand(data_files=inputs, data_frames=None, output_file=output_file)
    print(df)


if __name__ == "__main__":
    import pandas as pd

    pd.set_option("display.max_columns", None)
    app()
