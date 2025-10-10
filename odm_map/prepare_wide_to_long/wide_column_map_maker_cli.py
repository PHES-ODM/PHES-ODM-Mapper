from typing import Annotated
from pathlib import Path
import typer

from odm_map.prepare_wide_to_long.wide_column_map_maker import WideColumnMapMaker

app = typer.Typer(
    pretty_exceptions_show_locals=False,
    rich_markup_mode="rich",
)

MAIN_HELP = """Create LinkML-Map schemas for mapping from expanded wide format to
ODM long format."""

INPUT_HELP = """Path to data file that the generated LinkML-Map schemas should
map to ODM long format. This should be a wide format, after being processed
by the wide column expander."""

TARGET_SCHEMA_HELP = """Path to the LinkML schema that the target mapped data is for
(eg. for ODM v3 long format)."""

OUTPUT_DIR_HELP = """If specified, then the directory to save the LinkML-Map
schemas to."""

CONFIG_HELP = """The YAML configuration file."""

SOURCE_CLASS_HELP = """The name of the source class in the mapping."""


@app.command(help=MAIN_HELP)
def main(
    input: Annotated[Path, typer.Argument(show_default=False, help=INPUT_HELP)],
    config: Annotated[Path, typer.Option(show_default=False, help=CONFIG_HELP)],
    target_schema: Annotated[
        Path, typer.Option(show_default=False, help=TARGET_SCHEMA_HELP)
    ],
    source_class: Annotated[
        str, typer.Option(show_default=False, help=SOURCE_CLASS_HELP)
    ],
    output_dir: Annotated[
        Path, typer.Option(show_default=False, help=OUTPUT_DIR_HELP)
    ] = None,
):
    maker = WideColumnMapMaker(
        config=config, source_class_name=source_class, target_schema=target_schema
    )
    maker.make(data_file=input, data_frame=None, output_dir=output_dir)


if __name__ == "__main__":
    app()
